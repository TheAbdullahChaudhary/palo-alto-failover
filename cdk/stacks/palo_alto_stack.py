import aws_cdk as cdk
from aws_cdk import (
    Stack,
    aws_lambda as _lambda,
    aws_iam as iam,
    aws_events as events,
    aws_events_targets as targets,
    aws_ssm as ssm,
    aws_ec2 as ec2,
    Duration
)
from constructs import Construct
import yaml
import os

class PaloAltoStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, customer: str, stage: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        self.customer = customer
        self.stage = stage
        
        # Load config
        config_path = f"../config/{customer}-{stage}.yml"
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        # Common tags
        self.common_tags = {
            "Customer": customer,
            "Application": "palo-alto-failover",
            "Team": "Knights/Pathfinders Squad",
            "Stage": stage,
            "Framework": "CDK",
            "PHI": "true",
            "Environment": f"{customer}-{stage}",
            "Version": "1.1.0"
        }
        
        # Apply tags to stack
        for key, value in self.common_tags.items():
            cdk.Tags.of(self).add(key, value)
        
        # Get VPC configuration from SSM
        self.vpc_config = self._get_vpc_config()
        
        # Create Lambda layer
        self.lambda_layer = self._create_lambda_layer()
        
        # Create Lambda functions
        self.health_check_function = self._create_health_check_function()
        self.failover_function = self._create_failover_function()
        self.sync_config_function = self._create_sync_config_function()
        
        # Create schedules and add dependencies
        self._create_schedules()
        
        # Create SSM parameters for function ARNs
        self._create_ssm_parameters()
        
        # Add dependencies to ensure proper deployment order
        self.health_check_function.node.add_dependency(self.lambda_layer)
        self.failover_function.node.add_dependency(self.lambda_layer)
        self.sync_config_function.node.add_dependency(self.lambda_layer)
    
    def _get_vpc_config(self):
        return {
            "security_group_id": ssm.StringParameter.value_for_string_parameter(
                self, f"/{self.customer}/{self.stage}/lambda/sg/id"
            ),
            "subnet_ids": ssm.StringListParameter.value_for_string_list_parameter(
                self, f"/{self.customer}/{self.stage}/vpc/subnets/lambda/ids"
            )
        }
    
    def _create_lambda_layer(self):
        return _lambda.LayerVersion(
            self, "PythonRequirementsLayer",
            layer_version_name=f"palo-alto-failover-layer-{self.customer}-{self.stage}",
            description="Palo Alto Failover Python requirements lambda layer",
            code=_lambda.Code.from_asset("../", bundling=cdk.BundlingOptions(
                image=_lambda.Runtime.PYTHON_3_13.bundling_image,
                command=[
                    "bash", "-c",
                    "pip install poetry && "
                    "poetry config virtualenvs.create false && "
                    "poetry install --only=main && "
                    "mkdir -p /asset-output/python && "
                    "cp -r /opt/python/lib/python3.13/site-packages/* /asset-output/python/ || true"
                ]
            )),
            compatible_runtimes=[_lambda.Runtime.PYTHON_3_13]
        )
    
    def _create_health_check_function(self):
        role = iam.Role(
            self, "HealthCheckRole",
            role_name=f"palo-alto-health-check-{self.customer}-{self.stage}-lambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaVPCAccessExecutionRole"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AWSXRayDaemonWriteAccess")
            ],
            inline_policies={
                "HealthCheckPolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=["secretsmanager:GetSecretValue"],
                            resources=[ssm.StringParameter.value_for_string_parameter(
                                self, "/palo_alto/secret/api_access/arn"
                            )]
                        ),
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=["ssm:GetParameter", "ssm:DescribeParameter"],
                            resources=[
                                f"arn:aws:ssm:{self.region}:{self.account}:parameter/palo_alto/instance/active/id",
                                f"arn:aws:ssm:{self.region}:{self.account}:parameter/palo_alto/*/interface/management/id",
                                f"arn:aws:ssm:{self.region}:{self.account}:parameter/palo_alto/sns/failover/arn"
                            ]
                        ),
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=["lambda:InvokeFunction"],
                            resources=[f"arn:aws:lambda:{self.region}:{self.account}:function:palo-alto-failover-{self.customer}-{self.stage}"]
                        ),
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=["sns:Publish"],
                            resources=[ssm.StringParameter.value_for_string_parameter(
                                self, "/palo_alto/sns/failover/arn"
                            )]
                        )
                    ]
                )
            }
        )
        
        function = _lambda.Function(
            self, "HealthCheckFunction",
            function_name=f"palo-alto-health-check-{self.customer}-{self.stage}",
            runtime=_lambda.Runtime.PYTHON_3_13,
            handler="lambda_functions.palo_alto_health_check.src.lambda_function.lambda_handler",
            code=_lambda.Code.from_asset("../"),
            layers=[self.lambda_layer],
            role=role,
            timeout=Duration.minutes(5),
            reserved_concurrent_executions=1,
            vpc=ec2.Vpc.from_lookup(self, "VPC", is_default=False),
            vpc_subnets=ec2.SubnetSelection(subnet_ids=self.vpc_config["subnet_ids"]),
            security_groups=[ec2.SecurityGroup.from_security_group_id(
                self, "HealthCheckSG", self.vpc_config["security_group_id"]
            )],
            environment={
                "VERSION": "1.1.0",
                "LOG_LEVEL": "INFO",
                "ENVIRONMENT": self.stage,
                "REGION": self.region,
                "CUSTOMER": self.customer,
                "PALO_ALTO_SECRET_NAME": ssm.StringParameter.value_for_string_parameter(
                    self, "/palo_alto/secret/api_access/name"
                ),
                "CLIENT_NAME": self.customer,
                "FAILOVER_FUNCTION": f"palo-alto-failover-{self.customer}-{self.stage}",
                "SNS_FAILOVER_TOPIC": ssm.StringParameter.value_for_string_parameter(
                    self, "/palo_alto/sns/failover/arn"
                ),
                "FAILOVER_TEST": "False"
            }
        )
        
        return function
    
    def _create_failover_function(self):
        role = iam.Role(
            self, "FailoverRole",
            role_name=f"palo-alto-failover-{self.customer}-{self.stage}-lambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaVPCAccessExecutionRole"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AWSXRayDaemonWriteAccess")
            ],
            inline_policies={
                "FailoverPolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "ec2:DisassociateAddress", "ec2:DescribeInstances", "ec2:DescribeAddresses",
                                "ec2:DescribeTags", "ec2:Describe*", "ec2:CreateTags", "ec2:DeleteNetworkInterface",
                                "ec2:AssignPrivateIpAddresses", "ec2:StopInstances", "ec2:ReplaceRoute",
                                "ec2:CreateNetworkInterface", "ec2:DescribeNetworkInterfaces", "ec2:StartInstances",
                                "ec2:DescribeNetworkInterfaceAttribute", "ec2:DescribeSubnets", "ec2:AssociateAddress",
                                "ec2:DescribeRouteTables"
                            ],
                            resources=["*"]
                        ),
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=["ssm:GetParameter", "ssm:PutParameter"],
                            resources=[
                                f"arn:aws:ssm:{self.region}:{self.account}:parameter/palo_alto/instance/active/id",
                                f"arn:aws:ssm:{self.region}:{self.account}:parameter/palo_alto/instance/list/ids",
                                f"arn:aws:ssm:{self.region}:{self.account}:parameter/palo_alto/*/interface/internal/id",
                                f"arn:aws:ssm:{self.region}:{self.account}:parameter/palo_alto/*/interface/external/id"
                            ]
                        )
                    ]
                )
            }
        )
        
        function = _lambda.Function(
            self, "FailoverFunction",
            function_name=f"palo-alto-failover-{self.customer}-{self.stage}",
            runtime=_lambda.Runtime.PYTHON_3_13,
            handler="lambda_functions.palo_alto_failover.src.lambda_function.lambda_handler",
            code=_lambda.Code.from_asset("../"),
            layers=[self.lambda_layer],
            role=role,
            timeout=Duration.minutes(15),
            vpc=ec2.Vpc.from_lookup(self, "FailoverVPC", is_default=False),
            vpc_subnets=ec2.SubnetSelection(subnet_ids=self.vpc_config["subnet_ids"]),
            security_groups=[ec2.SecurityGroup.from_security_group_id(
                self, "FailoverSG", self.vpc_config["security_group_id"]
            )],
            environment={
                "VERSION": "1.1.0",
                "LOG_LEVEL": "INFO",
                "ENVIRONMENT": self.stage,
                "REGION": self.region,
                "CUSTOMER": self.customer,
                "PALO_ACTIVE_INSTANCE_SSM": "/palo_alto/instance/active/id",
                "PALO_INSTANCE_LIST_SSM": "/palo_alto/instance/list/ids",
                "PALO_EIP_ID": ssm.StringParameter.value_for_string_parameter(
                    self, "/palo_alto/eip/public/id"
                )
            }
        )
        
        return function
    
    def _create_sync_config_function(self):
        role = iam.Role(
            self, "SyncConfigRole",
            role_name=f"palo-alto-sync-config-{self.customer}-{self.stage}-lambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaVPCAccessExecutionRole"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AWSXRayDaemonWriteAccess")
            ],
            inline_policies={
                "SyncConfigPolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=["secretsmanager:GetSecretValue"],
                            resources=[ssm.StringParameter.value_for_string_parameter(
                                self, "/palo_alto/secret/api_access/arn"
                            )]
                        ),
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=["ssm:GetParameter"],
                            resources=[
                                f"arn:aws:ssm:{self.region}:{self.account}:parameter/palo_alto/instance/active/id",
                                f"arn:aws:ssm:{self.region}:{self.account}:parameter/palo_alto/instance/list/ids",
                                f"arn:aws:ssm:{self.region}:{self.account}:parameter/palo_alto/*/interface/management/id",
                                f"arn:aws:ssm:{self.region}:{self.account}:parameter/palo_alto/*/interface/internal/id"
                            ]
                        ),
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=["s3:*"],
                            resources=[
                                f"arn:aws:s3:::{self.customer}-{self.stage}-palo-configs/*",
                                f"arn:aws:s3:::{self.customer}-{self.stage}-palo-configs"
                            ]
                        ),
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=["ec2:Describe*", "ec2:StartInstances", "ec2:StopInstances"],
                            resources=["*"]
                        ),
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=["sns:Publish"],
                            resources=[ssm.StringParameter.value_for_string_parameter(
                                self, "/palo_alto/sns/config_sync/arn"
                            )]
                        )
                    ]
                )
            }
        )
        
        function = _lambda.Function(
            self, "SyncConfigFunction",
            function_name=f"palo-alto-sync-config-{self.customer}-{self.stage}",
            runtime=_lambda.Runtime.PYTHON_3_13,
            handler="lambda_functions.palo_alto_sync_config.src.lambda_function.lambda_handler",
            code=_lambda.Code.from_asset("../"),
            layers=[self.lambda_layer],
            role=role,
            timeout=Duration.minutes(15),
            vpc=ec2.Vpc.from_lookup(self, "SyncConfigVPC", is_default=False),
            vpc_subnets=ec2.SubnetSelection(subnet_ids=self.vpc_config["subnet_ids"]),
            security_groups=[ec2.SecurityGroup.from_security_group_id(
                self, "SyncConfigSG", self.vpc_config["security_group_id"]
            )],
            environment={
                "VERSION": "1.1.0",
                "LOG_LEVEL": "INFO",
                "ENVIRONMENT": self.stage,
                "REGION": self.region,
                "CUSTOMER": self.customer,
                "PALO_ALTO_SECRET_NAME": ssm.StringParameter.value_for_string_parameter(
                    self, "/palo_alto/secret/api_access/name"
                ),
                "PALO_ACTIVE_INSTANCE_SSM": "/palo_alto/instance/active/id",
                "PALO_ACTIVE_INTERFACE_SSM": "/palo_alto/ACTIVE_INSTANCE_ID/interface/management/id",
                "PALO_INSTANCE_LIST_SSM": "/palo_alto/instance/list/ids",
                "PALO_SNS_TOPIC_ARN": ssm.StringParameter.value_for_string_parameter(
                    self, "/palo_alto/sns/config_sync/arn"
                ),
                "PALO_CONFIG_S3_BUCKET": f"{self.customer}-{self.stage}-palo-configs",
                "XML_PREFIX": self.config.get("xmlPrefix", "<?xml version=\"1.0\"?>"),
                "CONFIG_FILENAME": self.config.get("configFilename", "paloconfig.xml")
            }
        )
        
        return function
    
    def _create_schedules(self):
        # Health check schedule
        health_check_rule = events.Rule(
            self, "HealthCheckSchedule",
            rule_name=f"palo-alto-health-check-{self.customer}-{self.stage}",
            description="Triggers lambda for verifying palo status",
            schedule=events.Schedule.rate(Duration.minutes(
                self.config.get("healthCheckInterval", 5)
            )),
            enabled=self.config.get("healthCheckEnabled", True)
        )
        health_check_rule.add_target(targets.LambdaFunction(self.health_check_function))
        
        # Sync config schedule
        sync_config_rule = events.Rule(
            self, "SyncConfigSchedule",
            rule_name=f"palo-alto-sync-config-{self.customer}-{self.stage}",
            description="Triggers lambda for syncing palo alto configs",
            schedule=events.Schedule.rate(Duration.hours(
                self.config.get("syncConfigInterval", 24)
            )),
            enabled=self.config.get("syncConfigEnabled", True)
        )
        sync_config_rule.add_target(targets.LambdaFunction(self.sync_config_function))
    
    def _create_ssm_parameters(self):
        ssm.StringParameter(
            self, "HealthCheckArnParam",
            parameter_name=f"/{self.customer}/{self.stage}/palo-alto-failover/palo_alto/health_check/arn",
            string_value=self.health_check_function.function_arn
        )
        
        ssm.StringParameter(
            self, "FailoverArnParam",
            parameter_name=f"/{self.customer}/{self.stage}/palo-alto-failover/palo_alto/failover/arn",
            string_value=self.failover_function.function_arn
        )
        
        ssm.StringParameter(
            self, "SyncConfigArnParam",
            parameter_name=f"/{self.customer}/{self.stage}/palo-alto-failover/palo_alto/sync_config/arn",
            string_value=self.sync_config_function.function_arn
        )
