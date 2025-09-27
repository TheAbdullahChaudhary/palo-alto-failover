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
        self.PALO_ACTIVE_INSTANCE_SSM = os.getenv('PALO_ACTIVE_INSTANCE_SSM', '')
        self.PALO_ACTIVE_INTERFACE_SSM = os.getenv('PALO_ACTIVE_INTERFACE_SSM','')
        self.PALO_INSTANCE_LIST_SSM = os.getenv('PALO_INSTANCE_LIST_SSM','')
        self.PALO_SNS_TOPIC_ARN = os.getenv('PALO_SNS_TOPIC_ARN','')
        self.PALO_CONFIG_S3_BUCKET = os.getenv('PALO_CONFIG_S3_BUCKET','')
        self.XML_PREFIX = os.getenv('XML_PREFIX','')
        self.CONFIG_FILENAME = os.getenv('CONFIG_FILENAME','')

config = Config()