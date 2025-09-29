# Palo Alto Failover

An automated failover system for Palo Alto firewalls using AWS Lambda functions. This system monitors firewall health and triggers failover processes to ensure high availability.

## Table of Contents
- [Overview](#overview)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Deployment](#deployment)
- [Usage](#usage)
- [Monitoring](#monitoring)
- [Troubleshooting](#troubleshooting)
- [Development](#development)
- [Contributing](#contributing)

## Overview

This system provides automated failover capabilities for Palo Alto firewalls by:
- Continuously monitoring firewall health status
- Detecting failures and network issues
- Automatically triggering failover to backup firewalls
- Synchronizing configurations between primary and backup units
- Providing logging and alerting for all failover events

## Architecture

The system consists of several AWS Lambda functions:
- **Health Check**: Monitors firewall status and connectivity
- **Failover**: Handles the actual failover process
- **Config Sync**: Synchronizes configurations between firewalls
- **Utils**: Common utilities and helper functions

## Prerequisites

Before you begin, ensure you have:

- **Python 3.13+**
- **Poetry 2.1.0+** for dependency management
- **Node.js 18+** and **npm 9+**
- **AWS CLI** configured with appropriate permissions
- **Serverless Framework** installed globally
- **AWS Account** with necessary IAM permissions

### Required AWS Permissions
- Lambda function creation and management
- IAM role creation and management
- CloudWatch logs access
- VPC and networking permissions (if applicable)

## Installation

1. **Clone the repository:**
```bash
git clone https://github.com/TheAbdullahChaudhary/palo-alto-failover.git
cd palo-alto-failover
```

2. **Install Python dependencies:**
```bash
poetry install
```

3. **Install Node.js dependencies:**
```bash
npm install
```

4. **Install Serverless Framework globally (if not already installed):**
```bash
npm install -g serverless
```

## Configuration

1. **Configure AWS credentials:**
```bash
aws configure
```

2. **Update configuration files:**
   - Edit `config/config.yaml` with your firewall details
   - Update `serverless.yml` with your AWS account and region settings
   - Modify environment-specific variables in the config directory

3. **Environment Variables:**
Create a `.env` file with required variables:
```bash
PALO_ALTO_PRIMARY_IP=<primary-firewall-ip>
PALO_ALTO_BACKUP_IP=<backup-firewall-ip>
PALO_ALTO_USERNAME=<username>
PALO_ALTO_PASSWORD=<password>
AWS_REGION=<your-aws-region>
```

## Deployment

### Quick Deployment
Use the provided deployment script:
```bash
./deploy.sh <customer> <stage>
```

Example:
```bash
./deploy.sh national dev
```

### Manual Deployment
1. **Deploy using Serverless:**
```bash
serverless deploy --stage <stage>
```

2. **Deploy specific function:**
```bash
serverless deploy function --function healthCheck --stage <stage>
```

### Environment-Specific Deployment
- **Development:** `./deploy.sh customer dev`
- **Staging:** `./deploy.sh customer staging`
- **Production:** `./deploy.sh customer prod`

## Usage

### Health Check Monitoring
The health check function runs automatically based on the configured schedule (default: every 5 minutes).

### Manual Failover
To trigger a manual failover:
```bash
aws lambda invoke --function-name palo-alto-failover-<stage>-failover response.json
```

### Configuration Sync
To manually sync configurations:
```bash
aws lambda invoke --function-name palo-alto-failover-<stage>-syncConfig response.json
```

### Viewing Logs
```bash
serverless logs --function healthCheck --stage <stage>
serverless logs --function failover --stage <stage>
```

## Monitoring

### CloudWatch Metrics
The system creates custom CloudWatch metrics for:
- Firewall health status
- Failover events
- Configuration sync status
- Response times

### Alarms
Configure CloudWatch alarms for:
- Failed health checks
- Failover events
- Function errors
- High response times

### Dashboard
Access the CloudWatch dashboard to monitor:
- System health overview
- Recent failover events
- Performance metrics
- Error rates

## Troubleshooting

### Common Issues

1. **Connection Timeouts:**
   - Check firewall network connectivity
   - Verify security group rules
   - Confirm VPC configuration

2. **Authentication Failures:**
   - Verify credentials in environment variables
   - Check firewall user permissions
   - Ensure API access is enabled

3. **Deployment Errors:**
   - Verify AWS credentials and permissions
   - Check serverless.yml configuration
   - Ensure all dependencies are installed

### Debug Mode
Enable debug logging by setting:
```bash
export DEBUG=true
```

### Log Analysis
Check CloudWatch logs for detailed error information:
```bash
aws logs describe-log-groups --log-group-name-prefix "/aws/lambda/palo-alto-failover"
```

## Development

### Project Structure
```
palo-alto-failover/
├── lambda_functions/
│   ├── palo_alto_health_check/
│   ├── palo_alto_failover/
│   ├── palo_alto_sync_config/
│   └── palo_alto_utils/
├── config/
├── tests/
├── serverless.yml
├── pyproject.toml
└── README.md
```

### Running Tests
```bash
poetry run pytest
```

### Code Quality
```bash
poetry run black .
poetry run flake8
poetry run mypy .
```

### Version Management
Update version numbers in:
- `serverless.yml`
- `package.json`
- `pyproject.toml`
- `sonar-project.properties`

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Make your changes and add tests
4. Run tests and ensure code quality checks pass
5. Commit your changes: `git commit -m 'Add feature'`
6. Push to the branch: `git push origin feature-name`
7. Submit a pull request

### Code Standards
- Follow PEP 8 for Python code
- Use type hints where applicable
- Write comprehensive tests
- Update documentation for new features

## AWS Services Used
- **AWS Lambda**: Serverless function execution
- **CloudWatch**: Logging and monitoring
- **IAM**: Access control and permissions
- **VPC**: Network isolation (optional)
- **Systems Manager**: Parameter storage

## Built With
- [Serverless Framework](https://serverless.com/) - AWS Services Manager
- [Poetry](https://python-poetry.org/) - Python Dependency Management
- [Boto3](https://boto3.amazonaws.com/) - AWS SDK for Python
- [Requests](https://requests.readthedocs.io/) - HTTP Library

## License
This project is licensed under the MIT License - see the LICENSE file for details.

## Support
For support and questions:
- Create an issue in this repository
- Contact the development team
- Check the troubleshooting section above
