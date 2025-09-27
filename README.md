# Palo Alto Failover

This repo contains code for checking the status of the Palo Alto and triggering the failover process.

### Prerequisites
Before you begin, ensure you have met the following requirements:

- Python3.13
- Poetry 2.1.0
- NPM 9+
- AWS Account Console Access


### Deployment Instructions
To deploy Palo Alto Failover, follow these steps:


**1\.** Fetch repository resources from bitbucket and checkout correct version

```
$ git clone git@gitlab.com:velatura/hie-platform/platform-supporting-infrastructure/palo-alto-failover.git
$ git checkout tags/v1.1.0
```

**2\.** Deploy the repository using the deployment script with the customer and stage as parameters:

```
$ cd palo-alto-failover/
$ ./deploy.sh national dev
```


### Operations

- Palo Alto Failover is now deployed.

### Testing / Logging

* TBD


### AWS Services Used
- Lambda: For periodic Health checks.
- IAM: Custom roles for each lambda function.


### Development Information
* **Version Number** - When deploying a new version, it is critical to adjust the version number accordingly. Make version updates in the following locations:

```
serverless.yml - Indicates the version to deploy.
package.json - Indicates build dependencies for serverless.
pyproject.toml
sonar-project.properties

* All four files should have the same version in them.
```


### Built With

* [Serverless](https://serverless.com/) - AWS Services Manager
* [Pip](https://pypi.org/project/pip/) - Dependency Management
* [Poetry](https://python-poetry.org/) - Dependency Management

### Authors

* [MiHIN](jason.brown@mihin.org) - **Jason Brown**
* [MiHIN](philip.wortinger@mihin.org) - **Phil Wortinger**

### License
*	This code is confidential proprietary trade secret of MiHIN. Copyright MiHIN 2021.
