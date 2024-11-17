import os
import boto3

def handler(event, context):
    instance_id = os.environ['INSTANCE_ID']
    ec2 = boto3.client('ec2')
    ec2.start_instances(InstanceIds=[instance_id])