import os
import boto3

from aws_cdk import (
    Duration,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_events as events,
    aws_events_targets as targets,
    aws_lambda as _lambda,
    Stack
)
from constructs import Construct

class SimpleTraderCdkStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        app_name = "SimpleTrader"
        s3_bucket_suffix = os.getenv("S3_BUCKET_SUFFIX", "")
        bucket_name = f"simpletrader-working-bucket{s3_bucket_suffix}"

        role = self.create_iam_role(app_name)

        # VPC for EC2
        vpc = ec2.Vpc.from_lookup(self, "DefaultVPC", is_default=True)

        # EC2 Instance
        instance = self.create_ec2_instance(app_name, vpc, role)

        # Automatically start and stop ec2 instance
        self.create_start_stop_role(instance, app_name, role, bucket_name)

        # Create Athena table for analyzing trading data
        self.create_athena_table(bucket_name)

    def create_ec2_instance(self, app_name, vpc, role):
        wd_path = f"/home/ec2-user/projects/{app_name}"
        instance_type_str = "c6g.2xlarge"
        key_pair_name = app_name + "KeyPair"

        ec2.CfnKeyPair(self, key_pair_name, key_name=key_pair_name)

        security_group = ec2.SecurityGroup(self, "SSHAccessSecurityGroup",
            vpc=vpc,  # Use the default VPC
            description="Allow SSH access on port 22",
            allow_all_outbound=True
        )
        security_group.add_ingress_rule(
            ec2.Peer.any_ipv4(),  # Allow from any IP (change this to a specific IP range for better security)
            ec2.Port.tcp(22),      # Allow port 22 (SSH)
            "Allow SSH access"
        )

        instance = ec2.Instance(
            self, app_name+"Instance",
            instance_type=ec2.InstanceType(f"{instance_type_str}"),  # Graviton processor
            machine_image=ec2.MachineImage.latest_amazon_linux2(cpu_type=ec2.AmazonLinuxCpuType.ARM_64),
            vpc=vpc,
            key_name=key_pair_name,
            security_group=security_group,
            role=role
        )

        # User Data Script for EC2 Instance
        # User Data script
        user_data_script = """
#!/bin/bash

sudo systemctl enable crond

sudo ln -sf /usr/share/zoneinfo/Asia/Kolkata /etc/localtime
sudo timedatectl set-timezone Asia/Kolkata

# Install development tools
sudo yum groupinstall "Development Tools" -y
sudo yum install gcc libffi-devel bzip2 bzip2-devel zlib-devel xz-devel wget make -y
sudo yum install openssl11-devel -y
sudo yum install -y openssl11
sudo yum install -y sqlite-devel

sudo yum remove -y openssl-devel

# Create the base directory if it doesn't exist
mkdir -p /home/ec2-user/installers

# Install python 3.9.6
cd /home/ec2-user/installers
sudo wget https://www.python.org/ftp/python/3.9.6/Python-3.9.6.tgz
sudo tar xzf Python-3.9.6.tgz

cd Python-3.9.6/

sudo make clean
sudo ./configure --enable-optimizations
sudo make altinstall
python3.9 -m ensurepip --upgrade
python3.9 -m pip install --upgrade pip

# Give back control to the user
sudo chown -R ec2-user:ec2-user /home/ec2-user/

# Create the cron job entries
echo "55 8 * * * ec2-user /bin/bash -c 'cd /home/ec2-user/projects/SimpleTrader; export PYTHONPATH\=/home/ec2-user/projects/SimpleTrader/src && /usr/local/bin/python3.9 /home/ec2-user/projects/SimpleTrader/src/setup/pre_market_setup.py 2>&1'" | sudo tee -a /etc/crontab
echo "14 9 * * * ec2-user /bin/bash -c 'cd /home/ec2-user/projects/SimpleTrader; export PYTHONPATH\=/home/ec2-user/projects/SimpleTrader/src && /usr/local/bin/python3.9 /home/ec2-user/projects/SimpleTrader/src/setup/setup.py 2>&1'" | sudo tee -a /etc/crontab

# Restart cron to apply the new jobs
sudo systemctl restart crond
"""

        instance.add_user_data(user_data_script)

        # Allow EC2 to SSH
        instance.connections.allow_from_any_ipv4(ec2.Port.tcp(22), "Allow SSH")

        return instance

    def create_start_stop_role(self, instance, app_name, role, bucket_name):
        # https://aws-sdk-pandas.readthedocs.io/en/stable/layers.html
        lambda_layer_arn = "arn:aws:lambda:ap-south-1:336392948345:layer:AWSSDKPandas-Python39:26"

        # Create Lambda functions to start and stop the instance
        start_lambda = _lambda.Function(self, "Start"+app_name+"InstanceLambda",
            runtime=_lambda.Runtime.PYTHON_3_9,
            code=_lambda.Code.from_asset("lambda_functions/start"),
            handler="start.handler",
            role=role,
            timeout=Duration.seconds(300),  # Increase timeout to 5 minutes
            environment={
                "INSTANCE_ID": instance.instance_id,
                "BUCKET_NAME" : bucket_name,
                "APP_NAME" : app_name
            },
            layers=[_lambda.LayerVersion.from_layer_version_arn(self, "PandasLayer", lambda_layer_arn)],
        )

        stop_lambda = _lambda.Function(self, "Stop"+app_name+"InstanceLambda",
            runtime=_lambda.Runtime.PYTHON_3_9,
            code=_lambda.Code.from_asset("lambda_functions/stop"),
            handler="stop.handler",
            timeout=Duration.seconds(300),  # Increase timeout to 5 minutes
            role=role,
            environment={
                "INSTANCE_ID": instance.instance_id,
                "BUCKET_NAME" : bucket_name,
                "APP_NAME" : app_name
            }
        )

        # Create EventBridge rules to trigger Lambda functions
        start_rule = events.Rule(self, "StartRule",
            schedule=events.Schedule.cron(minute="15", hour="3", week_day="MON-FRI")  # Every weekday at 8:45AM IST / 3:15AM UTC. DST should not affect this
        )
        start_rule.add_target(targets.LambdaFunction(start_lambda))

        stop_rule = events.Rule(self, "StopRule",
            schedule=events.Schedule.cron(minute="10", hour="10", week_day="MON-FRI")  # Every weekday at 3:40PM IST / 10:10AM UTC. DST should not affect this
        )
        stop_rule.add_target(targets.LambdaFunction(stop_lambda))

    def create_iam_role(self, app_name):
        role = iam.Role(self, app_name+"Role",
                    assumed_by=iam.CompositePrincipal(
                        iam.ServicePrincipal("ec2.amazonaws.com"),  # EC2 can assume this role
                        iam.ServicePrincipal("lambda.amazonaws.com")  # Lambda can also assume this role
                    ),
                    description="Role required for services for running SimpleTrader application",
                    managed_policies=[
                        iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEC2FullAccess"),  # EC2 permissions
                        iam.ManagedPolicy.from_aws_managed_policy_name("AmazonS3FullAccess"),  # S3 permissions
                        iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore")  # Add SSM permissions
                    ]
        )

        role.add_to_policy(
            iam.PolicyStatement(
                sid="Statement1",
                effect=iam.Effect.ALLOW,
                actions=["ssm:SendCommand"],
                resources=[
                    f"arn:aws:ec2:{self.region}:{self.account}:instance/*",
                    f"arn:aws:ssm:{self.region}::document/AWS-RunShellScript",
                ],
            )
        )

        role.add_to_policy(
            iam.PolicyStatement(
                sid="Statement2",
                effect=iam.Effect.ALLOW,
                actions=["ssm:GetCommandInvocation"],
                resources=[
                    f"arn:aws:ssm:{self.region}:{self.account}:*"
                ],
            )
        )

        return role

    def create_athena_table(self, bucket_name: str):
        glue_client = boto3.client('glue')
        
        # Create database if it doesn't exist
        try:
            glue_client.create_database(
                DatabaseInput={
                    'Name': 'trading_analytics'
                }
            )
        except glue_client.exceptions.AlreadyExistsException:
            pass

        # Create table
        table_input = {
            'Name': 'order_ledger',
            'TableType': 'EXTERNAL_TABLE',
            'Parameters': {
                'classification': 'csv',
                'typeOfData': 'file',
                'areColumnsQuoted': 'false',
                'delimiter': ',',
                'skip.header.line.count': '1'
            },
            'StorageDescriptor': {
                'Location': f's3://{bucket_name}/SimpleTraderLedger/',
                'InputFormat': 'org.apache.hadoop.mapred.TextInputFormat',
                'OutputFormat': 'org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat',
                'SerdeInfo': {
                    'SerializationLibrary': 'org.apache.hadoop.hive.serde2.lazy.LazySimpleSerDe',
                    'Parameters': {
                        'serialization.format': ',',
                        'field.delim': ',',
                        'timestamp.formats': 'yyyy-MM-dd HH:mm:ss'
                    }
                },
                'Columns': [
                    {'Name': 'symbol', 'Type': 'string'},
                    {'Name': 'entry_time', 'Type': 'timestamp'},
                    {'Name': 'entry_price', 'Type': 'double'},
                    {'Name': 'entry_qty', 'Type': 'int'},
                    {'Name': 'entry_type', 'Type': 'string'},
                    {'Name': 'entry_value', 'Type': 'double'},
                    {'Name': 'entry_tag', 'Type': 'string'},
                    {'Name': 'exit_time', 'Type': 'timestamp'},
                    {'Name': 'exit_price', 'Type': 'double'},
                    {'Name': 'exit_qty', 'Type': 'int'},
                    {'Name': 'exit_type', 'Type': 'string'},
                    {'Name': 'exit_value', 'Type': 'double'},
                    {'Name': 'exit_tag', 'Type': 'string'},
                    {'Name': 'buy_price', 'Type': 'double'},
                    {'Name': 'sell_price', 'Type': 'double'},
                    {'Name': 'buy_value', 'Type': 'double'},
                    {'Name': 'sell_value', 'Type': 'double'},
                    {'Name': 'charges', 'Type': 'double'},
                    {'Name': 'gross_pnl', 'Type': 'double'},
                    {'Name': 'net_pnl', 'Type': 'double'}
                ]
            }
        }

        try:
            glue_client.create_table(
                DatabaseName='trading_analytics',
                TableInput=table_input
            )
            print("Successfully created Athena table")
        except glue_client.exceptions.AlreadyExistsException:
            print("Table already exists. Updating schema...")
            glue_client.update_table(
                DatabaseName='trading_analytics',
                TableInput=table_input
            )
            print("Successfully updated Athena table")
