import os
from aws_cdk import (
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_s3 as s3,
    aws_events as events,
    aws_events_targets as targets,
    aws_ssm as ssm,
    aws_lambda as _lambda,
    Stack,
    RemovalPolicy
    # aws_sqs as sqs,
)
from constructs import Construct

class SimpleTraderCdkStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        app_name = "SimpleTrader"
        bucket_name = "simpletrader-working-bucket"

        role = self.create_iam_role(app_name)

        # VPC for EC2
        vpc = ec2.Vpc.from_lookup(self, "DefaultVPC", is_default=True)

        # EC2 Instance
        instance = self.create_ec2_instance(app_name, vpc, role, bucket_name)

        # Automatically start and stop ec2 instance
        self.create_start_stop_role(instance, app_name, role)

    def create_ec2_instance(self, app_name, vpc, role, bucket_name):
        repo_key = "repo.zip"
        config_key = "config.py"
        requirements_key = "requirements.txt"
        wd_path = f"/home/ec2-user/projects/{app_name}"
        instance_type_str = "c6g.2xlarge"
        key_pair_name = app_name + "KeyPair"
        repo_local_path = f"{wd_path}/repo.zip"

        key_pair = ec2.CfnKeyPair(self, key_pair_name, key_name=key_pair_name)

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
        instance.user_data.add_commands(
            # Step 1: Remove existing directory
            f"rm -rf {wd_path}",
            f"echo \"Copying repo {repo_key} from bucket {bucket_name} to {repo_local_path}\"",

            # Step 2: Download and unzip repo.zip
            f"aws s3 cp s3://{bucket_name}/{repo_key} {repo_local_path}",
            f"mkdir -p {wd_path}",
            f"unzip {repo_local_path} -d {wd_path}",

            # Step 3: Download config.py
            f"echo \"Copying config.py from bucket {bucket_name} to {wd_path}/src/{config_key}\"",
            f"aws s3 cp s3://{bucket_name}/{config_key} {wd_path}/src/{config_key}",

            # Step 4: Download requirements.txt
            f"echo \"Copying requirements.txt from bucket {bucket_name} to {wd_path}/{requirements_key}\"",
            f"aws s3 cp s3://{bucket_name}/{requirements_key} {wd_path}/{requirements_key}",

            # Step 5: Create virtual environment and install dependencies
            f"cd {wd_path}",
            "python3 -m venv venv",
            "source venv/bin/activate",
            "pip install -r requirements.txt",

            # Step 6: Run setup.py
            "python setup/setup.py",

            # Step 7: Wait for market start and execute trade.py
            "echo 'Waiting for market start time...'"
        )

        # Allow EC2 to SSH
        instance.connections.allow_from_any_ipv4(ec2.Port.tcp(22), "Allow SSH")

        return instance

    def create_start_stop_role(self, instance, app_name, role):
        # Create Lambda functions to start and stop the instance
        start_lambda = _lambda.Function(self, "Start"+app_name+"InstanceLambda",
            runtime=_lambda.Runtime.PYTHON_3_9,
            code=_lambda.Code.from_asset("lambda_functions/start"),
            handler="lambda_function.handler",
            role=role,
            environment={
                "INSTANCE_ID": instance.instance_id
            }
        )

        stop_lambda = _lambda.Function(self, "Stop"+app_name+"InstanceLambda",
            runtime=_lambda.Runtime.PYTHON_3_9,
            code=_lambda.Code.from_asset("lambda_functions/stop"),
            handler="lambda_function.handler",
            role=role,
            environment={
                "INSTANCE_ID": instance.instance_id
            }
        )

        # Create EventBridge rules to trigger Lambda functions
        start_rule = events.Rule(self, "StartRule",
            schedule=events.Schedule.cron(minute="31", hour="2", week_day="MON-FRI")  # Every weekday at 8:01AM IST / 2:31AM UTC. DST should not affect this
        )
        start_rule.add_target(targets.LambdaFunction(start_lambda))

        stop_rule = events.Rule(self, "StopRule",
            schedule=events.Schedule.cron(minute="25", hour="10", week_day="MON-FRI")  # Every weekday at 3:55PM IST / 10:25AM UTC. DST should not affect this
        )
        stop_rule.add_target(targets.LambdaFunction(stop_lambda))

    def create_iam_role(self, app_name):
        return iam.Role(self, app_name+"Role",
                    assumed_by=iam.CompositePrincipal(
                        iam.ServicePrincipal("ec2.amazonaws.com"),  # EC2 can assume this role
                        iam.ServicePrincipal("lambda.amazonaws.com")  # Lambda can also assume this role
                    ),
                    description="Role required for services for running SimpleTrader application",
                    managed_policies=[
                        iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEC2FullAccess"),  # EC2 permissions
                        iam.ManagedPolicy.from_aws_managed_policy_name("AmazonS3ReadOnlyAccess")  # S3 permissions
                    ]
        )