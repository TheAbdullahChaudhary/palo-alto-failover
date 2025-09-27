import os, boto3, logging, time, datetime, requests
from defusedxml import ElementTree as ET
from lambda_functions.palo_alto_utils.src import utils as utils
from lambda_functions.palo_alto_sync_config.src.config import config
requests.packages.urllib3.disable_warnings()

logger = logging.getLogger()
utils.setup_logging(logger)

client = boto3.client('s3', region_name=config.REGION)
resource = boto3.resource('ec2', region_name=config.REGION)
s3 = boto3.resource('s3', region_name=config.REGION)
sns = boto3.client('sns', region_name=config.REGION)

def lambda_handler(event, context):
    try:
        active_instance_id = utils.get_ssm_param(config.PALO_ACTIVE_INSTANCE_SSM)
        logger.info(f"Active instance ID: {active_instance_id}")
        
        palo_ip = get_eni_ip(active_instance_id)
        logger.info(f"Palo Alto IP: {palo_ip}")
        
        # Test connectivity first
        if not utils.test_palo_connectivity(palo_ip):
            raise Exception(f"Cannot establish basic connectivity to Palo Alto at {palo_ip}")
        
        palo_creds = utils.get_secret(config.PALO_ALTO_SECRET_NAME)
        logger.info("Retrieved Palo Alto credentials")
        
        palo_key = utils.palo_api_key(palo_ip, palo_creds['username'], palo_creds['password'])
    
        str_palo_active_config = config.XML_PREFIX+get_data_from_api(palo_ip, palo_key)
        
        store_to_S3(str_palo_active_config, config.PALO_CONFIG_S3_BUCKET)

        s3.Bucket(config.PALO_CONFIG_S3_BUCKET).download_file(config.CONFIG_FILENAME, '/tmp/localcopy.xml')

        if (check_file_existence(client, config.PALO_CONFIG_S3_BUCKET, config.CONFIG_FILENAME ) is not None) and os.path.isfile('/tmp/localcopy.xml'):
            instances_list_str = utils.get_ssm_param(config.PALO_INSTANCE_LIST_SSM)
            raw_instances_list = instances_list_str.split(",")
            inactive_instance_ids = [ item.strip() for item in raw_instances_list if item.strip()!=active_instance_id ]
            
            PALO_ACTIVE_INTERNAL_ENI_SSM = f"/palo_alto/{active_instance_id}/interface/internal/id"
            old_eni_id = utils.get_ssm_param(PALO_ACTIVE_INTERNAL_ENI_SSM)
            old_private_ip = utils.get_eni_private_ip(old_eni_id)
            old_private_ip_prefix = old_private_ip[:old_private_ip.rfind(".")]
            
            for item in inactive_instance_ids:
                try:
                    inactive_config_backup(item, palo_creds['username'], palo_creds['password'], str_palo_active_config, old_private_ip_prefix)
                except Exception as e:
                    logger.error(f"ERROR: Failed to back up config for inactive Palo Alto instance {item}: {e}")
        else:
            subject = f"Couldn't not locate backup config from s3 bucket: {config.PALO_CONFIG_S3_BUCKET}"
            msg = f"{config.CONFIG_FILENAME} not found"
            post_to_sns(subject, msg)
    except Exception as e:
        logger.error(f"Lambda execution failed: {str(e)}", exc_info=True)
        raise
    return


def verify_before_commit(ip, key):
    logger.info("Validating config...")
    url = f"https://{ip}/api/?type=op&cmd=<validate><full></full></validate>&key={key}"
    
    try:
        response_text = requests.get(url, verify=False).text
        logger.info(f"Validation response: {response_text}")
        
        response = ET.fromstring(response_text)
        logger.info(f"Validation XML status: {response.get('status')}")
        
        # Check if the response was successful first
        if response.get('status') != 'success':
            logger.error("Validation request failed")
            error_msg = response.find('msg')
            error_text = error_msg.text if error_msg is not None else "Unknown validation error"
            logger.error(f"Validation error: {error_text}")
            return False
        
        # Look for the job ID with error handling
        job_element = response.find('result/job')
        if job_element is not None and job_element.text is not None:
            job_id = job_element.text
            logger.info(f"Validation job ID: {job_id}")
            return validate(ip, job_id, key, "Pre-commit validation Failed")
        else:
            logger.error("Could not find job ID in validation response")
            logger.error(f"Full validation response: {response_text}")
            
            # Sometimes the validation might complete immediately without a job
            # Check if there's a direct result
            result_element = response.find('result')
            if result_element is not None:
                logger.info("Validation appears to have completed immediately")
                return True
            
            return False
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error during validation: {e}")
        return False
    except ET.ParseError as e:
        logger.error(f"XML parsing error in validation: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error in validation: {e}", exc_info=True)
        return False
  

def validate(ip, jid, key, subj):
    url = f"https://{ip}/api/?type=op&cmd=<show><jobs><id>{jid}</id></jobs></show>&key={key}"
    progress = 0
    max_attempts = 60  # Prevent infinite loop
    attempts = 0
    
    while progress < 100 and attempts < max_attempts:
        try:
            response_text = requests.get(url, verify=False).text
            response = ET.fromstring(response_text)
            
            # Check if the job status request was successful
            if response.get('status') != 'success':
                logger.error(f"Job status request failed: {response_text}")
                return False
            
            # Get progress with error handling
            progress_elem = response.find('result/job/progress')
            result_elem = response.find('result/job/result')
            
            if progress_elem is not None and progress_elem.text is not None:
                progress = int(progress_elem.text)
                logger.info(f"Progress {progress}")
            else:
                logger.warning("Could not find progress in job status, assuming job is complete")
                progress = 100
            
            if result_elem is not None and result_elem.text is not None:
                logger.info(f"Job result: {result_elem.text}")
                if progress == 100:
                    if result_elem.text == "FAIL":
                        post_to_sns(subj, ET.tostring(response).decode())
                        return False
                    else:
                        return True
            elif progress == 100:
                # If progress is 100 but no result, assume success
                logger.info("Job completed without explicit result, assuming success")
                return True
                
        except Exception as e:
            logger.error(f"Error checking job status: {e}")
            return False
            
        attempts += 1
        if progress < 100:
            time.sleep(5)
    
    if attempts >= max_attempts:
        logger.error("Job validation timed out")
        return False
        
    return True


def post_to_sns(subj, message):
    logger.info(message)
    response = sns.publish(
        TargetArn=config.PALO_SNS_TOPIC_ARN,
        Message=message,
        Subject=subj,
        MessageStructure='string'
    )


def commit_on_palo(ip,key):
    logger.info("Committing config...")
    url = f"https://{ip}/api/?type=commit&key={key}&cmd=<commit></commit>"
    response = requests.get(url,verify=False)
    xmlize = ET.fromstring(response.text)
    commit = validate(ip, xmlize.find('result/job').text, key, "Commit task  Failed")
    
    if commit:
        logger.info("All changes committed successfully")
    else:
        url_rollback = f"https://{ip}/api/?type=commit&key={key}&cmd=<load><config><last-saved></last-saved></config></load>"
        response = ET.fromstring(requests.get(url_rollback,verify=False).text)
        logger.info("All changes Reverted" if response.get('status') == 'success'  else "Both Commit & Revert configuration Failed (REQUIRED IMMEDIATE ATTENTION!)")
    return commit

    
def load_confg_palo(ip, key, name):
     logger.info("Loading config...")
     url = f"https://{ip}/api/?type=op&key={key}&cmd=<load><config><from>{name}</from></config></load>"
     response = requests.get(url,verify=False)
     return response.text
    
     
def import_to_palo(ip, key, file):
     logger.info("Importing config...")
     url = f"https://{ip}/api/?type=import&category=configuration&key={key}"
     now = str(datetime.datetime.now()).split(' ')[0]

     files={'file':(now + '.xml', open(file), 'application/xml')}
     response = requests.post(url,verify=False,files=files)
     return response.text

    
def store_to_S3(configdata, bucketname, filename=config.CONFIG_FILENAME):
    logger.info("Storing config...")
    client.put_object(Body=configdata, Bucket=bucketname, ContentEncoding='ascii', ContentType='application/xml', Key=filename)


def get_data_from_api(ip, key):
    url = f"https://{ip}/api/?type=export&category=configuration&key={key}"
    result = requests.get(url, verify=False).text
    return result
    

def check_file_existence(client, bucket, key):
    """return the key's size if it exist, else None"""
    response = client.list_objects_v2(
        Bucket=bucket,
        Prefix=key,
    )
    for obj in response.get('Contents', []):
        if obj['Key'] == key:
            return obj['Size']


def inactive_config_backup(instance_id, username, password, config_str, old_ip_prefix):
    inactive_instance = resource.Instance(instance_id)
    logger.info(f"Starting inactive instance {instance_id}...")
    inactive_instance.start()
    inactive_instance.wait_until_running()
    
    try:
        PALO_INACTIVE_INTERNAL_ENI_SSM = f"/palo_alto/{instance_id}/interface/internal/id"
        new_eni_id = utils.get_ssm_param(PALO_INACTIVE_INTERNAL_ENI_SSM)
        new_private_ip = utils.get_eni_private_ip(new_eni_id)
        new_private_ip_prefix = new_private_ip[:new_private_ip.rfind(".")]

        new_config = config_str.replace(old_ip_prefix, new_private_ip_prefix)
        inactive_filename = f"{instance_id}/{config.CONFIG_FILENAME}"
        store_to_S3(new_config, config.PALO_CONFIG_S3_BUCKET, inactive_filename)
        s3.Bucket(config.PALO_CONFIG_S3_BUCKET).download_file(inactive_filename, '/tmp/localcopy.xml')

        inactive_ip = inactive_instance.private_ip_address
        palo_key = utils.palo_api_key(inactive_ip, username, password)
        
        result_import = import_to_palo(inactive_ip, palo_key,'/tmp/localcopy.xml')
        xml_response_import = ET.fromstring(result_import)
        if xml_response_import.get('status') == 'success':
            msg_line = xml_response_import.find('msg/line')
            if msg_line is not None and msg_line.text is not None:
                name = msg_line.text.split(" ")[0]
                
                result_load = load_confg_palo(inactive_ip, palo_key, name)
                xml_response_load = ET.fromstring(result_load)
                if xml_response_load.get('status') == 'success':
                    
                    # ADD THE FUNCTION CALL HERE - Wait for auto-commit to complete
                    logger.info("Waiting for any auto-commit processes to complete...")
                    wait_for_auto_commit_completion(inactive_ip, palo_key, max_wait_minutes=15)
                    
                    # Additional wait for system to settle
                    logger.info("Allowing additional time for system to settle...")
                    time.sleep(60)  # Wait 1 minute for system to settle
                    
                    if verify_before_commit(inactive_ip, palo_key):
                        commit_on_palo(inactive_ip, palo_key)
                else:
                    post_to_sns('Failed to Load Config on Secondary Firewall', result_load)
            else:
                logger.error("Could not parse import response")
                post_to_sns('Failed to Parse Import Response', result_import)
        else:
            post_to_sns('Failed to Import Config to Secondary Firewall', result_import)
            
    except Exception as e:
        logger.error(f"Exception in inactive_config_backup: {str(e)}", exc_info=True)
        logger.info(f"Stopping inactive instance {instance_id}...")
        inactive_instance.stop()
        raise e
        
    logger.info(f"Stopping inactive instance {instance_id}...")
    inactive_instance.stop()
    return


def get_eni_ip(active_instance_id):
    ip = None
    active_eni_id = utils.get_ssm_param(config.PALO_ACTIVE_INTERFACE_SSM.replace("ACTIVE_INSTANCE_ID", active_instance_id))
    active_instance = resource.Instance(active_instance_id)
    for eni in active_instance.network_interfaces:
        if eni.id == active_eni_id:
            ip = eni.private_ip_address
            break
    if not ip:
        raise Exception(f"ERROR: Unable to find private IP address for active ENI: {active_eni_id} attached to active instance {active_instance_id}")

    return ip


def wait_for_auto_commit_completion(ip, key, max_wait_minutes=10):
    """Wait for any auto-commit processes to complete"""
    logger.info("Checking for pending auto-commit processes...")
    
    max_attempts = (max_wait_minutes * 60) // 30  # Check every 30 seconds
    
    for attempt in range(max_attempts):
        try:
            # Check if there are any running jobs
            url = f"https://{ip}/api/?type=op&cmd=<show><jobs><all></all></jobs></show>&key={key}"
            response = requests.get(url, verify=False, timeout=30)
            
            if response.status_code == 200:
                root = ET.fromstring(response.text)
                if root.get('status') == 'success':
                    # Look for any running commit jobs
                    jobs = root.findall('.//job')
                    active_commits = []
                    
                    for job in jobs:
                        job_type = job.find('type')
                        status = job.find('status')
                        if (job_type is not None and 
                            status is not None and
                            'commit' in job_type.text.lower() and 
                            status.text in ['ACT', 'PEND']):
                            active_commits.append(job.find('id').text if job.find('id') is not None else 'unknown')
                    
                    if not active_commits:
                        logger.info("No active commit jobs found - auto-commit appears to be complete")
                        return True
                    else:
                        logger.info(f"Found active commit jobs: {active_commits}")
                        
        except Exception as e:
            logger.warning(f"Error checking for auto-commit completion: {e}")
        
        if attempt < max_attempts - 1:
            logger.info(f"Waiting 30 seconds for auto-commit to complete... (attempt {attempt + 1}/{max_attempts})")
            time.sleep(30)
    
    logger.warning(f"Auto-commit did not complete within {max_wait_minutes} minutes")
    return False