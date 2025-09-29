import aws_cdk as cdk
from aws_cdk import assertions
from stacks.palo_alto_stack import PaloAltoStack
import pytest

def test_lambda_functions_created():
    app = cdk.App()
    stack = PaloAltoStack(app, "test-stack", customer="test", stage="dev")
    template = assertions.Template.from_stack(stack)
    
    # Test that 3 Lambda functions are created
    template.resource_count_is("AWS::Lambda::Function", 3)
    
    # Test Lambda layer is created
    template.resource_count_is("AWS::Lambda::LayerVersion", 1)

def test_iam_roles_created():
    app = cdk.App()
    stack = PaloAltoStack(app, "test-stack", customer="test", stage="dev")
    template = assertions.Template.from_stack(stack)
    
    # Test that 3 IAM roles are created (one for each Lambda)
    template.resource_count_is("AWS::IAM::Role", 3)

def test_eventbridge_rules_created():
    app = cdk.App()
    stack = PaloAltoStack(app, "test-stack", customer="test", stage="dev")
    template = assertions.Template.from_stack(stack)
    
    # Test that 2 EventBridge rules are created
    template.resource_count_is("AWS::Events::Rule", 2)

def test_ssm_parameters_created():
    app = cdk.App()
    stack = PaloAltoStack(app, "test-stack", customer="test", stage="dev")
    template = assertions.Template.from_stack(stack)
    
    # Test that 3 SSM parameters are created
    template.resource_count_is("AWS::SSM::Parameter", 3)

def test_lambda_function_names():
    app = cdk.App()
    stack = PaloAltoStack(app, "test-stack", customer="test", stage="dev")
    template = assertions.Template.from_stack(stack)
    
    # Test Lambda function names
    template.has_resource_properties("AWS::Lambda::Function", {
        "FunctionName": "palo-alto-health-check-test-dev"
    })
    
    template.has_resource_properties("AWS::Lambda::Function", {
        "FunctionName": "palo-alto-failover-test-dev"
    })
    
    template.has_resource_properties("AWS::Lambda::Function", {
        "FunctionName": "palo-alto-sync-config-test-dev"
    })
