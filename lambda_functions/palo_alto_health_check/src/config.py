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
        self.PALO_ALTO_SECRET_NAME = os.getenv('PALO_ALTO_SECRET_NAME', '')
        self.SNS_FAILOVER_TOPIC = os.getenv('SNS_FAILOVER_TOPIC', '')
        self.FAILOVER_FUNCTION = os.getenv('FAILOVER_FUNCTION', '')
        self.CLIENT_NAME = os.getenv('CLIENT_NAME', '')
        self.FAILOVER_TEST = os.getenv('FAILOVER_TEST', False).lower() == "true"

config = Config()