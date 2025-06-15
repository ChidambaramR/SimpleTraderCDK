rm -f AnalyticsEC2KeyPair.pem

KEY_PAIR_ID=$(aws ec2 describe-key-pairs --filters Name=key-name,Values=AnalyticsKeyPair --query "KeyPairs[0].KeyPairId" --output text)

echo "Found KeyPairId: $KEY_PAIR_ID"

aws ssm get-parameter --name "/ec2/keypair/$KEY_PAIR_ID" --with-decryption --query "Parameter.Value" --output text > AnalyticsEC2KeyPair.pem

chmod 400 AnalyticsEC2KeyPair.pem

echo "PEM file saved as AnalyticsEC2KeyPair.pem"