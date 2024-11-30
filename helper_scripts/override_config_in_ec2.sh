# NOTE
# Update 'config.py' source location
IP=$(aws ec2 describe-instances --query 'Reservations[*].Instances[*].PublicIpAddress' --output text) ; scp -i SimpleTraderEC2KeyPair.pem /Users/ajith/Desktop/Stocks/SimpleTrader/src/config.py ec2-user@$IP:/home/ec2-user/projects/SimpleTrader/src/config.py