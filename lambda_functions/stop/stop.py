import os
import boto3

def handler(event, context):
    instance_id = os.environ['INSTANCE_ID']
    ec2_client = boto3.client('ec2')
    ec2_client.stop_instances(InstanceIds=[instance_id])

    # Wait for the instance to enter the 'stopped' state
    print(f"Waiting for instance {instance_id} to be in 'stopped' state...")
    waiter = ec2_client.get_waiter('instance_stopped')
    waiter.wait(InstanceIds=[instance_id])
    print(f"Instance {instance_id} is now stopped.")

    return {
        'statusCode': 200,
        'body': f"Instance {instance_id} has been stopped successfully."
    }