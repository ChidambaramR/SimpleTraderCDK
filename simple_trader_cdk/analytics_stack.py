import os

from aws_cdk import (
    Duration,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_lambda as _lambda,
    Stack
)
from constructs import Construct

user_name = os.getenv("ANALYTICS_USER", "")
passw = os.getenv("ANALYTICS_PW", "")

EC2_SCRIPT = f"""#!/bin/bash
sudo yum update -y
sudo dnf install -y gcc openssl-devel bzip2-devel libffi-devel wget make nginx httpd-tools

# Python 3.9 comes pre-installed in t4g
python3 -m ensurepip
python3 -m pip install --upgrade pip
python3 -m pip install virtualenv flask

# Format and mount the additional EBS volume
DEVICE="/dev/nvme1n1"

echo "Formatting $DEVICE as ext4..."
sudo mkfs.ext4 $DEVICE

# Mount and persist
sudo mkdir -p /mnt/data
sudo mount $DEVICE /mnt/data
echo "$DEVICE /mnt/data ext4 defaults,nofail 0 2" | sudo tee -a /etc/fstab

sudo mkdir /mnt/data/analytics_db
sudo chown ec2-user:ec2-user /mnt/data/analytics_db

# Create .htpasswd file for basic auth
echo "Creating basic auth credentials..."
sudo htpasswd -bc /etc/nginx/.htpasswd {user_name} {passw}

# Start and enable Nginx
sudo systemctl enable nginx
sudo systemctl start nginx
"""


class AnalyticsStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        app_name = "Analytics"

        # EC2 Instance
        vpc = ec2.Vpc.from_lookup(self, "DefaultVPC", is_default=True)
        ec2_role = self.create_ec2_role()
        ec2_instance = self.create_ec2_instance(app_name, vpc, ec2_role)

        # Lambda
        lambda_role = self.create_lambda_role()
        self.create_website_lambdas(ec2_instance, lambda_role)


    def create_ec2_instance(self, app_name, vpc, ec2_role):
        instance_type_str = "t4g.large"
        key_pair_name = app_name + "KeyPair"

        ec2.CfnKeyPair(self, key_pair_name, key_name=key_pair_name)

        security_group = ec2.SecurityGroup(self, "AnalyticsSG",
            vpc=vpc,
            description="Allow SSH access on port 22, HTTP access on 80",
            allow_all_outbound=True
        )
        security_group.add_ingress_rule(
            ec2.Peer.any_ipv4(),
            ec2.Port.tcp(22),
            "Allow SSH access"
        )

        security_group.add_ingress_rule(
            ec2.Peer.any_ipv4(),
            ec2.Port.tcp(80),
            "Allow HTTP access for hosting"
        )

        instance = ec2.Instance(
            self, app_name+"Instance",
            instance_type=ec2.InstanceType(f"{instance_type_str}"),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(cpu_type=ec2.AmazonLinuxCpuType.ARM_64),
            vpc=vpc,
            key_name=key_pair_name,
            security_group=security_group,
            role=ec2_role
        )

        # Attach additional 24GB EBS volume
        instance.instance.add_property_override("BlockDeviceMappings", [
            {
                "DeviceName": "/dev/xvdb",
                "Ebs": {
                    "VolumeSize": 24,
                    "VolumeType": "gp3",
                    "DeleteOnTermination": True
                }
            }
        ])

        # User Data Script
        instance.add_user_data(EC2_SCRIPT)
        return instance

    def create_ec2_role(self):
        ec2_role = iam.Role(self, "EC2Role",
                    assumed_by=iam.CompositePrincipal(
                        iam.ServicePrincipal("ec2.amazonaws.com")  # EC2 can assume this role
                    ),
                    description="Role required for services for running SimpleTrader Analytics EC2",
                    managed_policies=[
                        iam.ManagedPolicy.from_aws_managed_policy_name("AmazonS3ReadOnlyAccess"),  # S3 permissions
                        iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore")  # Add SSM permissions
                    ]
        )
        return ec2_role

    def create_website_lambdas(self, ec2_instance, lambda_role):
        # Create Lambda function to start the EC2, register IP and domain name
        _lambda.Function(self, "StartWebsiteLambda",
            runtime=_lambda.Runtime.PYTHON_3_12,
            code=_lambda.Code.from_asset("lambda_functions/analytics_start"),
            handler="website_start.handler",
            role=lambda_role,
            timeout=Duration.seconds(600),  # Increase timeout to 10 minutes
            environment={
                "INSTANCE_ID": ec2_instance.instance_id
            }
        )

        # Create Lambda function to stop the EC2, deregister IP
        _lambda.Function(self, "StopWebsiteLambda",
            runtime=_lambda.Runtime.PYTHON_3_12,
            code=_lambda.Code.from_asset("lambda_functions/analytics_stop"),
            handler="website_stop.handler",
            role=lambda_role,
            timeout=Duration.seconds(600),  # Increase timeout to 10 minutes
            environment={
                "INSTANCE_ID": ec2_instance.instance_id
            }
        )


    def create_lambda_role(self):
        lambda_role = iam.Role(self, "LambdaRole",
                    assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
                    description="Role for Lambda to start EC2 and run SSM commands for SimpleTrader Analytics",
                    managed_policies=[
                        iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEC2FullAccess"),
                        iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMFullAccess")
                    ]
        )

        # Add inline policy for Route 53 and Elastic IP operations
        lambda_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "route53:ListHostedZonesByName",
                "route53:ChangeResourceRecordSets"
            ],
            resources=["*"]
        ))

        return lambda_role

