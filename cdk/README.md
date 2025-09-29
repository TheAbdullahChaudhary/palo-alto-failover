# Palo Alto Failover CDK Implementation

This directory contains the AWS CDK implementation of the Palo Alto Failover system, converted from the original Serverless Framework configuration.

## Architecture

The CDK implementation creates the following resources organized in a single stack:

### Lambda Functions
- **Health Check Function**: Monitors Palo Alto firewall health
- **Failover Function**: Handles failover operations
- **Sync Config Function**: Synchronizes configurations

### Supporting Resources
- **Lambda Layer**: Python dependencies shared across functions
- **IAM Roles**: Individual roles for each Lambda with least-privilege permissions
- **EventBridge Rules**: Scheduled triggers for health checks and config sync
- **SSM Parameters**: Store function ARNs for reference

## Deployment

### Prerequisites
- AWS CLI configured
- CDK CLI installed (`npm install -g aws-cdk`)
- Python 3.13+
- Poetry (for dependency management)

### Deploy
```bash
cd cdk/
./deploy.sh [customer] [stage]
```

Example:
```bash
./deploy.sh national dev
```

### Manual Deployment
```bash
pip install -r requirements.txt
cdk deploy --context customer=national --context stage=dev
```

## Configuration

Configuration is loaded from `config/{customer}-{stage}.yml` files, maintaining compatibility with the original Serverless configuration.

## Testing

Run unit tests:
```bash
python -m pytest tests/
```

## Key Differences from Serverless

1. **Stack Organization**: All resources in a single stack for this application
2. **Layer Packaging**: Uses CDK bundling for Python dependencies
3. **IAM Roles**: Explicit role creation with inline policies
4. **VPC Configuration**: References existing VPC resources via SSM parameters
5. **Environment Variables**: Maintained compatibility with original Lambda code

## Best Practices Implemented

- Individual IAM roles per Lambda function
- Least-privilege permissions
- Resource tagging for compliance
- Dependency management with `add_dependency`
- Unit testing of infrastructure code
- Parameterized deployment for multiple environments
