import boto3
import os
import time

ec2_client = boto3.client('ec2')
ssm_client = boto3.client('ssm')
route53_client = boto3.client('route53')

S3_BUCKET = "simpletrader-working-bucket-ajith"
S3_KEY = "repo_analytics.zip"
TARGET_DIR = "/home/ec2-user"
DOMAIN_NAME = "simple-trader-analytics.click"
TAG_KEY = "Project"
TAG_VALUE = "SimpleTraderAnalytics"

# 1. Start EC2
def start_ec2(instance_id):
    status = ec2_client.describe_instance_status(InstanceIds=[instance_id])
    if not status['InstanceStatuses'] or status['InstanceStatuses'][0]['InstanceState']['Name'] != 'running':
        ec2_client.start_instances(InstanceIds=[instance_id])
        ec2_client.get_waiter('instance_status_ok').wait(InstanceIds=[instance_id])

# 2. Create Elastic IP if required
def associate_eip(instance_id):
    existing_eip = None
    for eip in ec2_client.describe_addresses()['Addresses']:
        tags = {tag['Key']: tag['Value'] for tag in eip.get('Tags', [])}
        if tags.get(TAG_KEY) == TAG_VALUE:
            existing_eip = eip
            break

    # Don't create if one is present already
    if existing_eip:
        allocation_id = existing_eip['AllocationId']
        public_ip = existing_eip['PublicIp']
        print(f"Reusing EIP: {public_ip}")
    else:
        # Allocate and tag new EIP
        eip_response = ec2_client.allocate_address(Domain='vpc')
        allocation_id = eip_response['AllocationId']
        public_ip = eip_response['PublicIp']

        ec2_client.create_tags(Resources=[allocation_id], Tags=[
            {'Key': TAG_KEY, 'Value': TAG_VALUE},
            {'Key': 'CreatedBy', 'Value': 'Lambda'}
        ])
        print(f"Allocated new EIP: {public_ip}")

    # Associate EIP to instance
    ec2_client.associate_address(InstanceId=instance_id, AllocationId=allocation_id)
    return public_ip

# 3. Update Route 53 record with Elastic IP
def update_route53(public_ip):
    # Update Route 53 A record
    hosted_zone = route53_client.list_hosted_zones_by_name(DNSName=DOMAIN_NAME)
    if not hosted_zone['HostedZones']:
        raise Exception(f"No hosted zone found for {DOMAIN_NAME}")
    hosted_zone_id = hosted_zone['HostedZones'][0]['Id'].split('/')[-1]

    route53_client.change_resource_record_sets(
        HostedZoneId=hosted_zone_id,
        ChangeBatch={
            "Comment": "Update A record to point to EC2",
            "Changes": [{
                "Action": "UPSERT",
                "ResourceRecordSet": {
                    "Name": DOMAIN_NAME,
                    "Type": "A",
                    "TTL": 300,
                    "ResourceRecords": [{"Value": public_ip}]
                }
            }]
        }
    )


# 4. Bootstrap flask app via SSM
def create_flask_app(instance_id):
    command = f"""#!/bin/bash
cd {TARGET_DIR}
rm -rf {TARGET_DIR}/analytics
mkdir -p analytics
cd analytics
aws s3 cp s3://{S3_BUCKET}/{S3_KEY} .
unzip -o repo_analytics.zip
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn flask

# Start Gunicorn
nohup gunicorn --bind 127.0.0.1:8000 app:app --access-logfile /mnt/data/analytics_logs/access.log --error-logfile /mnt/data/analytics_logs/error.log --log-level info > /mnt/data/analytics_logs/gunicorn.log 2>&1 &

sudo systemctl enable nginx
sudo systemctl start nginx

# Configure NGINX
sudo tee /etc/nginx/conf.d/flaskapp.conf > /dev/null <<'EOF'
server {{
    listen 80;
    server_name _;

    location / {{
        auth_basic "Restricted Access";
        auth_basic_user_file /etc/nginx/.htpasswd;

        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;

        if ($http_user_agent ~* (googlebot|bingbot|slurp|duckduckbot|baiduspider|yandex)) {{
            return 403;
        }}
    }}
}}
EOF

sudo nginx -t && sudo systemctl reload nginx

# Warmup call - important
curl -s -o /dev/null -w "%{{http_code}}" "http://127.0.0.1:8000/backtest/gaps/trading_gaps_leg2/run_test?from_date=2024-12-01&to_date=2024-12-31&stop_loss=5&take_profit=3&entry_time=09%3A17&trade_direction=ALL&initial_capital=100000" | grep -q '^2' && echo "Primer Succeeded" || echo "Primer failed"
    """

    output = ssm_client.send_command(
        InstanceIds=[instance_id],
        DocumentName="AWS-RunShellScript",
        Parameters={'commands': [command]},
    )

    return output

# Main method
def handler(event, context):
    INSTANCE_ID = os.environ['INSTANCE_ID']

    start_ec2(INSTANCE_ID)
    public_ip = associate_eip(INSTANCE_ID)
    update_route53(public_ip)
    response = create_flask_app(INSTANCE_ID)

    command_id = response['Command']['CommandId']
    output = None

    # Poll until the command finishes
    while (output is None or output.get('Status') in ['Pending', 'InProgress']):
        time.sleep(2)
        output = ssm_client.get_command_invocation(
            CommandId=command_id,
            InstanceId=INSTANCE_ID,
        )

    print("Command status:", output['Status'])
    print("Standard output:\n", output.get('StandardOutputContent', ''))
    print("Standard error:\n", output.get('StandardErrorContent', ''))

    return {"status": "Success", "details": f"Started EC2, EIP: {public_ip}, A record updated."}
