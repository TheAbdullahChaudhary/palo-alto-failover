import boto3
import json
import logging
import re
import requests
import urllib3
from time import sleep
from defusedxml import ElementTree as ET
from botocore.exceptions import ClientError
from botocore.config import Config
from lambda_functions.palo_alto_utils.src import utils as utils
from lambda_functions.palo_alto_health_check.src.config import config

logger = logging.getLogger()
utils.setup_logging(logger)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
requests.packages.urllib3.disable_warnings()

# Script Variables:
lambda_config = Config(retries={'max_attempts': 3})

# SSM
ssm_active_palo = "/palo_alto/instance/active/id"

# Boto Clients:
ssm_client = boto3.client('ssm', region_name=config.REGION)
sns_client = boto3.client('sns', region_name=config.REGION)
ec2_client = boto3.client('ec2', region_name=config.REGION)
lambda_client = boto3.client(
    service_name='lambda',
    region_name=config.REGION,
    config=lambda_config,
)


def lambda_handler(event, context):
    logger.debug(event)

    try:
        palo_secret = get_secret(config.PALO_ALTO_SECRET_NAME)
        active_palo_ssm = get_ssm(ssm_active_palo)
        active_palo_management_eni_ssm = get_ssm(f"/palo_alto/{active_palo_ssm}/interface/management/id")
        active_palo_management_ip = get_eni_private_ip(active_palo_management_eni_ssm)

        try:
            palo_status = palo_status_check(active_palo_management_ip, palo_secret["username"], palo_secret["password"], config.FAILOVER_TEST)
            if palo_status:
                logger.info(f"Invoking: {config.FAILOVER_FUNCTION}")
                send_sns(True, f'A Palo Alto failover has been initiated for: {active_palo_ssm}',f'The palo status check process for {active_palo_ssm} has failed. Check log group /aws/lambda/palo-alto-health-check-{config.CLIENT_NAME}-prod for details', config.SNS_FAILOVER_TOPIC)
                invoke_lambda(config.FAILOVER_FUNCTION)
                active_palo_ssm = get_ssm(ssm_active_palo)
                active_palo_management_eni_ssm = get_ssm(f"/palo_alto/{active_palo_ssm}/interface/management/id")
                active_palo_management_ip = get_eni_private_ip(active_palo_management_eni_ssm)
                try:
                    second_palo_status = palo_status_check(active_palo_management_ip, palo_secret["username"], palo_secret["password"], False)
                    if second_palo_status:
                        send_sns(True, f'The Palo Alto failover has failed: {active_palo_ssm}',f'The Palo Alto failover process has failed for: {active_palo_ssm}. Check log group /aws/lambda/palo-alto-health-check-{config.CLIENT_NAME}-prod for details', config.SNS_FAILOVER_TOPIC)
                    else:
                        send_sns(False, f'The Palo Alto failover process has completed.',f'The new active Palo Alto Instance Id is: {second_palo_status}. Check log group /aws/lambda/palo-alto-health-check-{config.CLIENT_NAME}-prod for details', config.SNS_FAILOVER_TOPIC)
                except Exception as e:
                    raise
            else:
                logger.info("Health check was a success.")
        except ValueError as e:
            logger.info(f"Invoking: {config.FAILOVER_FUNCTION}")
            invoke_lambda(config.FAILOVER_FUNCTION)
            active_palo_ssm = get_ssm(ssm_active_palo)
            active_palo_management_eni_ssm = get_ssm(f"/palo_alto/{active_palo_ssm}/interface/management/id")
            active_palo_management_ip = get_eni_private_ip(active_palo_management_eni_ssm)
            try:
                second_palo_status = palo_status_check(active_palo_management_ip, palo_secret["username"], palo_secret["password"], False)
                if palo_status:
                    send_sns(True, f'The Palo Alto failover has failed: {active_palo_ssm}', f'The Palo Alto failover process has failed for: {active_palo_ssm} has failed. Check log group /aws/lambda/palo-alto-health-check-{config.CLIENT_NAME}-prod for details', config.SNS_FAILOVER_TOPIC)
                else:
                    send_sns(False, f'The Palo Alto failover process has completed.', f'The new active Palo Alto Instance Id is: {second_palo_status}. Check log group /aws/lambda/palo-alto-health-check-{config.CLIENT_NAME}-prod for details', config.SNS_FAILOVER_TOPIC)
            except Exception as e:
                raise

        response = {
            "statusCode": 200,
            "body": json.dumps({
                "status": "Success"
            })
        }
    except Exception as e:
        err_msg = f"Error processing: {e}"
        logger.error(err_msg, exc_info=True)
        response = {
            "statusCode": 500,
            "body": json.dumps({
                "status": "Error",
                "message": err_msg
            })
        }
        send_sns(True, 'Palo Alto Heath check has failed to run.', f'The following exception was caught when running the Palo Alto heath check:\n{e}', config.SNS_FAILOVER_TOPIC)
    return response


def get_secret(secret_name):
    session = boto3.session.Session()
    secretsmanager_client = session.client(
        service_name='secretsmanager',
        region_name=config.REGION,
    )

    try:
        get_secret_value_response = secretsmanager_client.get_secret_value(
            SecretId=secret_name
        )
        logger.info("Retrieved Secret %s", secret_name)
        return json.loads(get_secret_value_response["SecretString"])
    except ClientError as e:
        err_msg = f"Couldn't get secret {secret_name}.\n{e}"
        logger.exception(err_msg)
        raise


# https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ssm/client/get_parameter.html
def get_ssm(ssm_name):
    try:
        ssm_response = ssm_client.get_parameter(
            Name=ssm_name
        )
        logger.info("Retrieved SSM Parameter %s.", ssm_name)
        return ssm_response["Parameter"]["Value"]
    except ClientError as e:
        logger.exception("Failed to pull SSM Parameter %s:\n%s", ssm_name, e)
        raise


# https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ec2/instance/index.html
def get_eni_private_ip(eni_id):
    try:
        describe_network_interface = ec2_client.describe_network_interfaces(
            NetworkInterfaceIds=[eni_id]
        )
        private_ip = describe_network_interface["NetworkInterfaces"][0]["PrivateIpAddress"]
        logger.info("Retrieved Private IP.\nEni: %s\n Private IP %s", eni_id, private_ip)
        return private_ip
    except ClientError as e:
        logger.exception("Failed to pull private IP from ENI %s:\n%s", eni_id, e)
        raise


# https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ec2/instance/index.html
def invoke_lambda(function_name, payload=None, get_log=False):
    try:
        invoke_response = lambda_client.invoke(
            FunctionName=function_name,
            InvocationType='RequestResponse',
            Payload=json.dumps(payload),
            LogType="Tail" if get_log else "None",
        )
        logger.info("Invoked function %s.", function_name)
    except ClientError as e:
        logger.exception("Couldn't invoke function %s.\n%s", function_name, e)
        raise
    return invoke_response


#  https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/sns/client/publish.html
def send_sns(urgent, subject, message, arn):
    if urgent is True:
        subject = 'Critical - ' + subject

    sns_message = {
        "default": message,
        "sms": message,
        "email": message,
    }

    try:
        sns_response = sns_client.publish(Subject=subject, Message=json.dumps(sns_message), MessageStructure="json", TopicArn=arn)
        logger.info("SNS sent.\n%s", sns_response['MessageId'])
    except ClientError as e:
        logger.exception("Error sending SNS: \n%s", e)
        raise
    return sns_response


def palo_api_key(host, palo_user, palo_pass):
    api_key_query = {'type': 'keygen', 'user': palo_user, 'password': palo_pass}
    api_key_url = f"https://{host}/api"

    try:
        api_key_response = requests.get(api_key_url, params=api_key_query)
        root = ET.fromstring(api_key_response.text)
        api_key = root.find('.//key').text
        logger.info("Retrieved Palo Alto api key.")
        return api_key
    except Exception as e:
        logger.exception("Error reaching Palo Alto api key url.\n%s", e)
        raise


def palo_get_os_version(host, api_key):
    os_version_url = f"https://{host}/api?type=version&key={api_key}"

    try:
        os_version_response = requests.get(os_version_url)
        root = ET.fromstring(os_version_response.text)
        os_version = root.find('.//sw-version').text
        os_version = os_version.rsplit('.', 1)[0]
        logger.info("Retrieved OS Version from Palo Alto: %s", os_version)
        return os_version
    except Exception as e:
        logger.exception("Error retrieving Palo Alto OS Version.\n%s", e)
        raise


def palo_status(os_version, host, api_key, failover_test):
    if failover_test:
        logger.info('Running failover test.')
        raise ValueError
    palo_status_url = f"https://{host}/restapi/v{os_version}/Device/VirtualSystems"
    palo_status_headers = {'X-PAN-KEY': api_key}

    try:
        status_response = requests.get(palo_status_url, headers=palo_status_headers)
        logger.info('Response from API:\n %s', status_response.text)
        logger.info('Status Code: %s', status_response.status_code)
        if re.match('^[2-3][0-9]{2}$', str(status_response.status_code)):
            logger.info('Palo Alto API reached')
            return False
        else:
            logger.exception('Unable to reach Palo Alto Rest API')
            raise ValueError
    except Exception as e:
        logger.exception('Unable to reach Palo Rest API.\n%s', e)
        raise ValueError
    return True


def palo_status_check(host, palo_user, palo_pass, failover_test):
    try:
        api_key = palo_api_key(host, palo_user, palo_pass)
        os_version = palo_get_os_version(host, api_key)
        retries = 0
        max_retries = 3
        palo_response = None
        while palo_response is None and retries < max_retries:
            palo_response = palo_status(os_version, host, api_key, failover_test)
        return palo_response
    except Exception as e:
        logger.exception('Unable to complete Palo Alto status check.\n%s', e)
        if retries < max_retries:
            retries += 1
            logger.info("Retrying...")
            sleep(30)
            pass
        else:
            logger.error("Failed all retries!")
            raise e
        raise
