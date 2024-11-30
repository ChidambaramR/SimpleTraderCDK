rm -f SimpleTraderEC2KeyPair.pem
aws ssm get-parameters-by-path --path "/ec2/keypair/" --recursive  --with-decryption --query "Parameters[0].Value" --output text > SimpleTraderEC2KeyPair.pem
chmod 400 SimpleTraderEC2KeyPair.pem