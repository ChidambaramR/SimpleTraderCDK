from aws_cdk import (
    Stack,
    aws_iam as iam,
    CfnOutput,
    aws_secretsmanager as secretsmanager,
    aws_lambda as lambda_,
    Duration
)
from constructs import Construct
import json

class IamStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        ############################################################
        # CDK Deployer IAM credentials #
        ############################################################
        cdk_deployer_group = iam.Group(self, "CdkDeployerGroup",
            group_name="cdk-deployer",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AWSCloudFormationFullAccess"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEC2FullAccess"),
                iam.ManagedPolicy.from_aws_managed_policy_name("IAMFullAccess"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonS3FullAccess"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AWSLambda_FullAccess"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEventBridgeFullAccess"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMFullAccess"),
            ]
        )

        # Create IAM Users
        cdk_deployer_user = iam.User(self, "CdkDeployerUser",
            user_name="cdk-deployer-user",
            groups=[cdk_deployer_group]
        )

        # Create access keys for both users
        cdk_deployer_access_key = iam.CfnAccessKey(self, "CdkDeployerAccessKey",
            user_name=cdk_deployer_user.user_name
        )

        # Output the access keys (these will be shown in the CloudFormation outputs)
        CfnOutput(self, "CdkDeployerUserAccessKeyId",
            value=cdk_deployer_access_key.ref,
            description="Access Key ID for CDK Deployer User"
        )

        CfnOutput(self, "CdkDeployerUserSecretAccessKey",
            value=cdk_deployer_access_key.attr_secret_access_key,
            description="Secret Access Key for CDK Deployer User"
        )

        # Store access keys in Secrets Manager with rotation
        secretsmanager.Secret(self, "CdkDeployerCredentials",
            secret_name="cdk-deployer-credentials",
            description="Access credentials for CDK deployer user",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template=json.dumps({
                    "access_key_id": cdk_deployer_access_key.ref,
                    "secret_access_key": cdk_deployer_access_key.attr_secret_access_key
                }),
                generate_string_key="dummy"  # This is required but won't be used
            )
        )

        ############################################################
        # Programmatic Access IAM User #
        ############################################################
        programmatic_access_group = iam.Group(self, "ProgrammaticAccessGroup",
            group_name="programmatic-access",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonS3FullAccess"),
            ]
        )
        programmatic_access_user = iam.User(self, "ProgrammaticAccessUser",
            user_name="programmatic-access-user",
            groups=[programmatic_access_group]
        )
        programmatic_access_key = iam.CfnAccessKey(self, "ProgrammaticAccessKey",
            user_name=programmatic_access_user.user_name
        )
        CfnOutput(self, "ProgrammaticAccessUserAccessKeyId",
            value=programmatic_access_key.ref,
            description="Access Key ID for Programmatic Access User"
        )

        CfnOutput(self, "ProgrammaticAccessUserSecretAccessKey",
            value=programmatic_access_key.attr_secret_access_key,
            description="Secret Access Key for Programmatic Access User"
        )

        secretsmanager.Secret(self, "ProgrammaticAccessCredentials",
            secret_name="programmatic-access-credentials",
            description="Access credentials for programmatic access user",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template=json.dumps({
                    "access_key_id": programmatic_access_key.ref,
                    "secret_access_key": programmatic_access_key.attr_secret_access_key
                }),
                generate_string_key="dummy"  # This is required but won't be used
            )
        )


 