import os
import boto3
import time

def handler(event, context):
    upload_logs_to_s3()
    
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

def upload_logs_to_s3():
    instance_id = os.environ['INSTANCE_ID']
    bucket_name = os.environ['BUCKET_NAME']
    app_name = os.environ['APP_NAME']

    commands = [
        f"echo \"Uploading log file to S3\"",
        f"CURRENT_DATE=$(date +%Y-%m-%d)",
        f"cd /home/ec2-user/projects/{app_name}; export PYTHONPATH\=/home/ec2-user/projects/{app_name}/src && /usr/local/bin/python3.9 /home/ec2-user/projects/{app_name}/src/setup/closure_setup.py",
        f"aws s3 cp /home/ec2-user/projects/{app_name}/trade_logs/$CURRENT_DATE/ s3://{bucket_name}/{app_name}Logs/$CURRENT_DATE/ --recursive",
        f"aws s3 cp /home/ec2-user/projects/{app_name}/ledger/ s3://{bucket_name}/{app_name}Ledger/ --recursive",
    ]

    ssm_client = boto3.client('ssm')

    try:
        # Send commands as a shell script
        response = ssm_client.send_command(
            InstanceIds=[instance_id],
            DocumentName="AWS-RunShellScript",  # Built-in SSM document for running shell scripts
            Parameters={"commands": commands},
        )
        
        # Get Command ID
        command_id = response['Command']['CommandId']
        print(f"Command sent: {command_id}")

        # Optionally, wait for the command to complete
        time.sleep(2)  # Small delay before checking status
        output = ssm_client.get_command_invocation(
            CommandId=command_id,
            InstanceId=instance_id,
        )
        print(f"Command output: {output['StandardOutputContent']}")
        
        return {"status": "Success", "details": output}
    except Exception as e:
        print(f"Error: {str(e)}")
        return {"status": "Failed", "error": str(e)}