#!/usr/bin/env python3
import os

import aws_cdk as cdk

from simple_trader_cdk.simple_trader_cdk_stack import SimpleTraderCdkStack
from simple_trader_cdk.analytics_stack import AnalyticsStack
from simple_trader_cdk.iam_stack import IamStack

app = cdk.App()

# Deploy IAM resources
IamStack(app, "SimpleTraderIamStack",
    env=cdk.Environment(account=os.getenv('CDK_DEFAULT_ACCOUNT'), region=os.getenv('CDK_DEFAULT_REGION')),
)

# Deploy main application stack
SimpleTraderCdkStack(app, "SimpleTraderCdkStack",
    env=cdk.Environment(account=os.getenv('CDK_DEFAULT_ACCOUNT'), region=os.getenv('CDK_DEFAULT_REGION')),
)

# Deploy main application stack
AnalyticsStack(app, "AnalyticsStack",
    env=cdk.Environment(account=os.getenv('CDK_DEFAULT_ACCOUNT'), region=os.getenv('CDK_DEFAULT_REGION')),
)

app.synth()
