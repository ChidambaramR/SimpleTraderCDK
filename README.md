
# Welcome to your CDK Python project!

This project tracks the AWS infrastructure used for SimpleTrader trading application

- Install aws clie and cdk cli locally in your MAC
- Checkout the package and do cdk bootstrap if you are running for the very first time
- Else, do cdk deploy and observe the diff
- The following will be created
  - EC2 machine
    - To access the ec2 machine through terminal
      - The key pair for ec2 machine will be present in the parameter store of AWS Systems manager ( AWS Systems Manager -> Parameter Store) in the namespace /ec2
      - Download the key pair ( aws ssm get-parameter --name "<parameter-name>" --with-decryption --query "Parameter.Value" --output text > SimpleTraderEC2KeyPair.pem )
      - Give permissions ( chmod 400 SimpleTraderEC2KeyPair.pem)
      - The public IP address can be found from AWS Console or the following command ( aws ec2 describe-instances --instance-ids i-019921037dd3c62e2 --query "Reservations[*].Instances[*].PublicIpAddress" --output text )
      - To SSH, use the command ( ssh -i SimpleTraderEC2KeyPair.pem ec2-user@13.233.197.98 )
      - To SCP, use the command ( scp -i SimpleTraderEC2KeyPair.pem <local-file-path> ec2-user@13.233.197.98:<remote-file-path> )
  - Lambda to start and stop the ec2 machine
  - Eventbridge rule to trigger the lambda
- NOTE: For now, we have to manually create a S3 bucket since cdk deploy is not updating the S3 bucket and this results in a failure or a rollback of the stack during deploy
  - Create a S3 bucket with name like `simpletrader-working-bucket-ajith`, the suffix `-ajith` is required as S3 mandates global uniqueness across all AWS accounts.
  - Setup Mac/Linux Environment Variable `s3_bucket_suffix` with the value like `-ajith`. This is used in CDK setup to use the bucket named with appropriate suffix.
- This is the high level flow the different components
  - The ec2 machine is created upon stack synthesis.
    - It sets up the machine for Python3.9 since the algorithm and trading platform was developed using Python3.9
    - We setup a couple of cron jobs to run before the trading hours start. This usually setsup the trade by downloading historical data for context
  - The event bridge triggers the lambda at designated times (few minutes before trading day start and few minutes after trading day end)
  - The start lambda does the following
    - Cleans the working directory (/home/ec2-user/projects/SimpleTrader) of the ec2 host to remove previous trading data
    - Redownloads the following
      - Latest code base from the S3 bucket
      - keys.json containing the aws api key and secret key
      - access_token.txt which contains that days access token obtained from Zerodha
      - Downloads requirements.txt from S3 bucket and sets up Python site-packages required
  - During trading time, the cron job starts the trading script

To add additional dependencies, for example other CDK libraries, just add
them to your `setup.py` file and rerun the `pip install -r requirements.txt`
command.

## Useful commands

 * `cdk ls`          list all stacks in the app
 * `cdk synth`       emits the synthesized CloudFormation template
 * `cdk deploy`      deploy this stack to your default AWS account/region
 * `cdk diff`        compare deployed stack with current state
 * `cdk docs`        open CDK documentation

Enjoy!
