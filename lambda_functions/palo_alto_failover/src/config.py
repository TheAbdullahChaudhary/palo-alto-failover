import os
import logging
from lambda_functions.palo_alto_utils.src import utils

logger = logging.getLogger()
utils.setup_logging(logger)


class Config:
    def __init__(self):
        # Environment Variables
        
        # General
        self.ACCOUNT_ID = os.getenv('ACCOUNT_ID', '')
        self.CUSTOMER = os.getenv('CUSTOMER', '')
        self.STAGE = os.getenv('STAGE', 'dev')
        self.LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
        self.REGION = os.getenv('REGION', 'us-east-1')
        self.ENVIRONMENT = os.getenv('ENVIRONMENT', 'national-dev')
        self.VERSION = os.getenv('VERSION', '')

        # Infrastructure Related
        self.PALO_ACTIVE_INSTANCE_SSM = os.getenv('PALO_ACTIVE_INSTANCE_SSM', '/palo_alto/instance/active/id')
        self.PALO_INSTANCE_LIST_SSM = os.getenv('PALO_INSTANCE_LIST_SSM', '/palo_alto/instance/list/ids')
        self.PALO_EIP_ID = os.getenv('PALO_EIP_ID', '')

config = Config()