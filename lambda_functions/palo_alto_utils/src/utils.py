import logging
from pythonjsonlogger.json import JsonFormatter
import requests
import boto3
import base64
import json
import os
from defusedxml import ElementTree as ET
from time import sleep

logger = logging.getLogger()

ssm = boto3.client('ssm', region_name=os.getenv('REGION', 'us-east-1'))
secretsmanager = boto3.client('secretsmanager', region_name=os.getenv('REGION', 'us-east-1'))
ec2_client = boto3.client('ec2', region_name=os.getenv('REGION', 'us-east-1'))


def palo_api_key(host, user, password):
    api_key_query = {'type': 'keygen','user': user, 'password': password}
    api_key_url = f"https://{host}/api"
    api_key = None
    retries = 0

    while not api_key and retries < 3:
        try:
            logger.info(f"Making request to {api_key_url}")
            api_key_response = requests.get(api_key_url, params=api_key_query)
            api_key_response.raise_for_status()
            root = ET.fromstring(api_key_response.text)
            api_key = root.find('.//key').text
            logger.info("Retrieved Palo Alto api key")
        except Exception as e:
            logger.error(f"Error reaching Palo Alto api key url")
            if retries < 3:
                retries += 1
                logger.info("Retrying...")
                sleep(60)
                pass
            else:
                logger.error("Failed all retries!")
                raise e

    return api_key


def get_eni_private_ip(eni_id):
    private_ip = None
    try:
        resp = ec2_client.describe_network_interfaces(NetworkInterfaceIds=[eni_id])
        private_ip = resp["NetworkInterfaces"][0]["PrivateIpAddress"]
    except Exception as e:
        logger.error(f"Failed to get private IP from ENI {eni_id}", exc_info=True)
        raise e
    return private_ip


def get_ssm_param(param):
    try: 
        resp = ssm.get_parameter(Name=param)
        param_val = resp['Parameter']['Value']
    except Exception as e:
        logger.error(f"Error retrieving parameter {param}: {e}", exc_info=True)
        return None
    return param_val


def update_ssm_param(param, val):
    try:
        ssm.put_parameter(Name=param, Value=val, Overwrite=True)
    except Exception as e:
        logger.info(f"Error updating parameter {param}: {e}")
        raise e


def get_secret(secret_name):
    logger.info(f'Loading secret: {secret_name}')
    secret = '{}'
    try:
        get_secret_value_response = secretsmanager.get_secret_value(SecretId=secret_name)
    except Exception:
        logger.error(f"Could not retrieve secret: {secret_name}", exc_info=True)
    else:
        if 'SecretString' in get_secret_value_response:
            secret = get_secret_value_response['SecretString']
        elif 'SecretBinary' in get_secret_value_response:
            secret = base64.b64decode(get_secret_value_response['SecretBinary'])
    return json.loads(secret)


def setup_logging(logger):
    for h in logger.handlers:
        logger.removeHandler(h)
    logHandler = logging.StreamHandler()
    formatter = JsonFormatter(
        fmt="%(levelname)s %(message)s %(funcName)s %(asctime)s %(exc_info)s %(pathname)s %(args)s"
    )
    logHandler.setFormatter(formatter)
    logger.addHandler(logHandler)
    logger.setLevel(os.getenv('LOG_LEVEL', 'INFO'))
    logging.getLogger('boto3').setLevel(logging.ERROR)
    logging.getLogger('botocore').setLevel(logging.ERROR)
    logging.getLogger('aws_xray_sdk').setLevel(logging.ERROR)
    logging.getLogger("urllib3").setLevel(logging.ERROR)
    logging.getLogger("requests").setLevel(logging.ERROR)
    logging.getLogger("rediscluster").setLevel(logging.ERROR)


setup_logging(logger)
