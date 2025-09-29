#!/usr/bin/env python3
import aws_cdk as cdk
from stacks.palo_alto_stack import PaloAltoStack

app = cdk.App()

customer = app.node.try_get_context("customer") or "national"
stage = app.node.try_get_context("stage") or "dev"

PaloAltoStack(
    app, 
    f"palo-alto-failover-{customer}-{stage}",
    customer=customer,
    stage=stage,
    env=cdk.Environment(region="us-east-1")
)

app.synth()
