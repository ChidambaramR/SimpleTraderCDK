INSTANCE_ID=$(aws ec2 describe-instances --query 'Reservations[*].Instances[*].InstanceId' --output text); aws ec2 start-instances --instance-ids $INSTANCE_ID