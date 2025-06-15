import os
import boto3

def handler(event, context):    
    instance_id = os.environ['INSTANCE_ID']
    ec2_client = boto3.client('ec2')

    # 1. Stop EC2 instance
    ec2_client.stop_instances(InstanceIds=[instance_id])
    print(f"Stopping instance {instance_id}...")

    # 2. Wait for the instance to stop
    print(f"Waiting for instance {instance_id} to be in 'stopped' state...")
    waiter = ec2_client.get_waiter('instance_stopped')
    waiter.wait(InstanceIds=[instance_id])
    print(f"Instance {instance_id} is now stopped.")

    # 3. Look for EIP tagged for this project and disassociate + release
    print("Searching for tagged Elastic IPs to release...")
    addresses = ec2_client.describe_addresses()['Addresses']
    for addr in addresses:
        tags = {tag['Key']: tag['Value'] for tag in addr.get('Tags', [])}
        if tags.get('Project') == 'SimpleTraderAnalytics':
            allocation_id = addr['AllocationId']
            association_id = addr.get('AssociationId')

            if association_id:
                print(f"Disassociating EIP: {addr['PublicIp']} (AssociationId: {association_id})")
                ec2_client.disassociate_address(AssociationId=association_id)

            print(f"Releasing EIP: {addr['PublicIp']} (AllocationId: {allocation_id})")
            ec2_client.release_address(AllocationId=allocation_id)

    return {
        'statusCode': 200,
        'body': f"Instance {instance_id} stopped and associated EIP (if any) released."
    }
