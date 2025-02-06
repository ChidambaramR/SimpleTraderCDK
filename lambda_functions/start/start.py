from datetime import datetime, timedelta, timezone
import os
import boto3
import time

import pandas as pd

def is_today_holiday():
    bse_holidays  = [
        pd.Timestamp("2024-01-26", tz="Asia/Kolkata"),  # Fri, Republic Day
        pd.Timestamp("2024-03-08", tz="Asia/Kolkata"),  # Fri, Mahashivratri
        pd.Timestamp("2024-03-25", tz="Asia/Kolkata"),  # Mon, Holi
        pd.Timestamp("2024-03-29", tz="Asia/Kolkata"),  # Fri, Good Friday
        pd.Timestamp("2024-04-11", tz="Asia/Kolkata"),  # Thu, Id-Ul-Fitr (Ramadan Eid)
        pd.Timestamp("2024-04-17", tz="Asia/Kolkata"),  # Wed, Shri Ram Navmi
        pd.Timestamp("2024-05-01", tz="Asia/Kolkata"),  # Wed, Maharashtra Din
        pd.Timestamp("2024-06-17", tz="Asia/Kolkata"),  # Mon, Bakri Id / Eid ul-Adha
        pd.Timestamp("2024-07-17", tz="Asia/Kolkata"),  # Wed, Moharram
        pd.Timestamp("2024-08-15", tz="Asia/Kolkata"),  # Thu, Independence Day
        pd.Timestamp("2024-10-02", tz="Asia/Kolkata"),  # Wed, Mahatma Gandhi Jayanti
        pd.Timestamp("2024-11-01", tz="Asia/Kolkata"),  # Fri, Diwali
        pd.Timestamp("2024-11-15", tz="Asia/Kolkata"),  # Fri, Guru Nanak's Birthday
        pd.Timestamp("2024-11-20", tz="Asia/Kolkata"),  # Wed, Maharashtra election
        pd.Timestamp("2024-12-25", tz="Asia/Kolkata"),  # Wed, Christmas
        pd.Timestamp("2025-02-26", tz="Asia/Kolkata"),  # Wed, Mahashivratri
        pd.Timestamp("2025-03-14", tz="Asia/Kolkata"),  # Fri, Holi
        pd.Timestamp("2025-03-31", tz="Asia/Kolkata"),  # Mon, Id-Ul-Fitr (Ramadan Eid)
        pd.Timestamp("2025-04-10", tz="Asia/Kolkata"),  # Thu, Shri Mahavir Jayanti
        pd.Timestamp("2025-04-14", tz="Asia/Kolkata"),  # Mon, Dr. Baba Saheb Ambedkar Jayanti
        pd.Timestamp("2025-04-18", tz="Asia/Kolkata"),  # Fri, Good Friday
        pd.Timestamp("2025-05-01", tz="Asia/Kolkata"),  # Thu, Maharashtra Day
        pd.Timestamp("2025-08-15", tz="Asia/Kolkata"),  # Fri, Independence Day
        pd.Timestamp("2025-08-27", tz="Asia/Kolkata"),  # Wed, Ganesh Chaturthi
        pd.Timestamp("2025-10-02", tz="Asia/Kolkata"),  # Thu, Mahatma Gandhi Jayanti/Dussehra
        pd.Timestamp("2025-10-21", tz="Asia/Kolkata"),  # Tue, Diwali Laxmi Pujan*
        pd.Timestamp("2025-10-22", tz="Asia/Kolkata"),  # Wed, Diwali-Balipratipada
        pd.Timestamp("2025-11-05", tz="Asia/Kolkata"),  # Wed, Prakash Gurpurb Sri Guru Nanak Dev
        pd.Timestamp("2025-12-25", tz="Asia/Kolkata"),  # Thu, Christmas
    ]
    
    end_datetime = pd.Timestamp(datetime.now().date(), tz="Asia/Kolkata")
    if end_datetime in bse_holidays:
        return True

    return False


def is_config_file_old(bucket_name, object_key):
    # Initialize S3 client
    s3_client = boto3.client('s3')
    
    try:
        # Fetch object metadata
        response = s3_client.head_object(Bucket=bucket_name, Key=object_key)
        
        # Extract the LastModified timestamp, in UTC for uniform handling
        last_modified = response['LastModified'].astimezone(timezone.utc)
        
        # Calculate the difference
        time_difference =  datetime.now(timezone.utc) - last_modified
        
        # Check if less than 18 hours
        is_file_old = time_difference > timedelta(hours=18)
        
        print(f"File '{object_key}' last modified on {last_modified}")
        print(f"Time difference: {time_difference}")
        print(f"Is the file uploaded less than 18 hours ago? {is_file_old}")
        
        return is_file_old

    except Exception as e:
        print(f"Error: {str(e)}")
        return None

def handler(event, context):
    instance_id = os.environ['INSTANCE_ID']
    bucket_name = os.environ['BUCKET_NAME']
    app_name = os.environ['APP_NAME']
    config_key = "config.py"
    config_pre_market_key = "config_pre_market.py"
    # if is_config_file_old(bucket_name, config_key):
    #     print("Not starting ec2 machine because config is not updated recently.")
    #     return {"status": "Success", "details": "Did not start ec2 machine because of no config updates in last 18 hours"}

    if is_today_holiday():
        print("Not starting ec2 machine because today is a holiday")
        return {"status": "Success", "details": "Did not start ec2 machine"}

    ec2_client = boto3.client('ec2')

    # Step 1: Check the current state of the instance and start if required
    response = ec2_client.describe_instances(InstanceIds=[instance_id])
    current_state = response['Reservations'][0]['Instances'][0]['State']['Name']
    print(f"Current state of instance {instance_id}: {current_state}")

    if current_state == 'running':
        print(f"Instance {instance_id} is already running. Skipping start.")
    else:
        # Start the instance
        print(f"Starting instance {instance_id}...")
        ec2_client.start_instances(InstanceIds=[instance_id])

        # Wait for the instance to enter the running state
        print(f"Waiting for instance {instance_id} to be in 'running' state...")
        waiter = ec2_client.get_waiter('instance_running')
        waiter.wait(InstanceIds=[instance_id])
        print(f"Instance {instance_id} is now running.")

    # Step 2: Prep the host by setting up the directories
    repo_key = "repo.zip"
    requirements_key = "requirements.txt"
    keysjson_key = "keys.json"
    wd_path = f"/home/ec2-user/projects/{app_name}"
    repo_local_path = f"{wd_path}/repo.zip"

    commands = [
            # Step 1: Remove existing directory
            f"rm -rf {wd_path}",

            # Step 2: Download and unzip repo.zip
            f"echo \"Copying repo {repo_key} from bucket {bucket_name} to {repo_local_path}\"",
            f"aws s3 cp s3://{bucket_name}/{repo_key} {repo_local_path}",
            f"mkdir -p {wd_path}",
            f"unzip {repo_local_path} -d {wd_path}",

            # Step 3: Download config.py and config_pre_market.py
            f"echo \"Copying config.py from bucket {bucket_name} to {wd_path}/src/{config_key}\"",
            f"aws s3 cp s3://{bucket_name}/{config_key} {wd_path}/src/{config_key}",
            f"echo \"Copying config_pre_market.py from bucket {bucket_name} to {wd_path}/src/{config_pre_market_key}\"",
            f"aws s3 cp s3://{bucket_name}/{config_pre_market_key} {wd_path}/src/{config_pre_market_key}",

            # Step 4: Download requirements.txt
            f"echo \"Copying requirements.txt from bucket {bucket_name} to {wd_path}/{requirements_key}\"",
            f"aws s3 cp s3://{bucket_name}/{requirements_key} {wd_path}/{requirements_key}",

            # Step 5: Download keys.json
            f"echo \"Copying keys.json from bucket {bucket_name} to {wd_path}/{keysjson_key}\"",
            f"aws s3 cp s3://{bucket_name}/{keysjson_key} {wd_path}/{keysjson_key}",

            # Step 6: install dependencies
            f"cd {wd_path}",
            "python3.9 -m pip install -r requirements.txt",

            # Step 7: Restore permissions since we created new directories
            "sudo chown -R ec2-user:ec2-user /home/ec2-user/",
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