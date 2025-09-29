#!/bin/bash

# CDK deployment script for Palo Alto Failover
set -e

CUSTOMER=${1:-national}
STAGE=${2:-dev}

echo "Deploying Palo Alto Failover CDK stack for customer: $CUSTOMER, stage: $STAGE"

# Install dependencies
pip install -r requirements.txt

# Package lambda functions
echo "Packaging lambda functions..."
cd ../
zip -r cdk/lambda_package.zip lambda_functions/ -x "**/__pycache__/*" "**/*.pyc"
cd cdk/

# Bootstrap CDK (if needed)
cdk bootstrap

# Deploy the stack
cdk deploy \
  --context customer=$CUSTOMER \
  --context stage=$STAGE \
  --require-approval never

echo "Deployment completed successfully!"
