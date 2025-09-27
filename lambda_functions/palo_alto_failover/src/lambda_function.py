import json, boto3, logging, time
from lambda_functions.palo_alto_utils.src import utils as utils
from lambda_functions.palo_alto_failover.src.config import config

logger = logging.getLogger()
utils.setup_logging(logger)

client = boto3.client('ec2', region_name=config.REGION)


def lambda_handler(event, context):
    try:
        logger.info(event)
        ev = event.get('active_instance_id', None) if event else None
        old_instance_id, new_instance_id, vpc_id = get_palo_instances(ev)
        logger.info(f"Active instance {old_instance_id} switching to {new_instance_id}")

        # Start the secondary Palo
        logger.info("Checking state for inactive instance...")
        inactive_state = check_state(new_instance_id)
        if inactive_state != "running":
            logger.info("Starting inactive instance...")
            client.start_instances(InstanceIds=[new_instance_id])
            wait_until_running(new_instance_id)
        logger.info("Inactive instance started.")

        update_eip(new_instance_id)        
        update_route_table(old_instance_id, new_instance_id, vpc_id)

        # Update SSM parameter with new active instance ID
        logger.info(f"New active instance {new_instance_id} is ready")
        logger.info("Updating SSM parameter with new active instance")
        utils.update_ssm_param(config.PALO_ACTIVE_INSTANCE_SSM, new_instance_id)
        return {
            'statusCode': 200,
            'body': json.dumps('Success')
        }
    except Exception as e:
        logger.error(f"Error with Palo Alto Failover process",exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({"Failure":f'ERROR:{e}'})
        }


def get_palo_instances(new_instance_id=None):

    active_instance_id = utils.get_ssm_param(config.PALO_ACTIVE_INSTANCE_SSM)

    instances_list_str = utils.get_ssm_param(config.PALO_INSTANCE_LIST_SSM)
    raw_instances_list = instances_list_str.split(",")
    instances_list = [item.strip() for item in raw_instances_list]
    inactive_instances_list = [item for item in instances_list if item != active_instance_id]

    active_az = "a"
    try:
        resp = client.describe_instances(InstanceIds=[active_instance_id])
        logger.info(resp)
        inst_info = resp['Reservations'][0]['Instances'][0]
        active_az = inst_info['Placement']['AvailabilityZone'][-1:]
    except Exception:
        pass

    vpc_id = None
    inst_dict = {}
    for inst in inactive_instances_list:
        try:
            resp = client.describe_instances(InstanceIds=[inst])
            logger.info(resp)
            inst_info = resp['Reservations'][0]['Instances'][0]
            item_az = inst_info['Placement']['AvailabilityZone'][-1:]
            inst_dict[item_az] = inst
            if not vpc_id:  # Assumes all instances are in the same VPC
                vpc_id = inst_info['VpcId']
                logger.info(f"Found VPC ID: {vpc_id}")
        except Exception:
            logger.error(f"Failed to get VPC ID for instance {inst}",exc_info=True)
            pass

    if not vpc_id:
        err_msg = "ERROR: Unable to find VPC ID for instances"
        logger.error(err_msg)
        raise Exception(err_msg)

    if new_instance_id:
        if new_instance_id in inactive_instances_list:
            return active_instance_id, new_instance_id, vpc_id
        else:
            logger.info(f"Instance ID {new_instance_id} not found in palo instance list, choosing different instance from list")

    if not inst_dict or not vpc_id:
        err_msg = "ERROR: No valid instances in list"
        logger.error(err_msg)
        raise Exception(err_msg)

    # sorted_instances = dict(sorted(inst_dict.items()))
    sorted_instances = dict(sorted(inst_dict.items(), key=lambda x: (x[0]<active_az,x[0])))

    next_key = next(iter(sorted_instances))
    new_inst = sorted_instances[next_key]
    logger.info("Sorted instances:")
    logger.info(sorted_instances)
    logger.info(f"Selecting {new_inst}")

    # TODO: Instance of returning the first instance in the list, we probably want to try each one in order

    return active_instance_id, new_inst, vpc_id


def update_eip(instance2_id):
    logger.info(f"Associating address {config.PALO_EIP_ID} with {instance2_id}")

    PALO_EXTERNAL_ENI_SSM = f"/palo_alto/{instance2_id}/interface/external/id"
    new_eni_id = utils.get_ssm_param(PALO_EXTERNAL_ENI_SSM)
    private_ip = utils.get_eni_private_ip(new_eni_id)

    # Associate EIP with new instance
    try:
        client.associate_address(
            AllocationId=config.PALO_EIP_ID,
            NetworkInterfaceId=new_eni_id,
            PrivateIpAddress=private_ip,
            #DryRun=True
        )
    except Exception as e:
        msg = "Request would have succeeded, but DryRun flag is set."
        if msg in f"{e}":
            pass
        else:
            raise e
    return


def update_route_table(old_instance_id, new_instance_id, vpcID):
    logger.info("Updating route tables...")

    PALO_ACTIVE_INTERNAL_ENI_SSM = f"/palo_alto/{old_instance_id}/interface/internal/id"
    old_eni_id = utils.get_ssm_param(PALO_ACTIVE_INTERNAL_ENI_SSM)
    #old_private_ip = utils.get_eni_private_ip(old_eni_id)

    PALO_INACTIVE_INTERNAL_ENI_SSM = f"/palo_alto/{new_instance_id}/interface/internal/id"
    new_eni_id = utils.get_ssm_param(PALO_INACTIVE_INTERNAL_ENI_SSM)
    #new_private_ip = utils.get_eni_private_ip(new_eni_id)

    # Update all route tables with routes pointing to the Palo
    route_tables = client.describe_route_tables(Filters=[{'Name':'vpc-id','Values':[vpcID,]}])
    for route_table in route_tables['RouteTables']:
        for route in route_table['Routes']:
            if route.get('NetworkInterfaceId', None) == old_eni_id:
                destinationCidrBlock = route['DestinationCidrBlock']
                routeTableId = route_table['RouteTableId']
                msg = f"Replacing route for table {routeTableId} and dest {destinationCidrBlock} with new instance ID {new_eni_id}"
                logger.info(msg)
                try:
                    client.replace_route(
                        DestinationCidrBlock=destinationCidrBlock,
                        #InstanceId=new_instance_id,
                        NetworkInterfaceId=new_eni_id,
                        RouteTableId=routeTableId,
                        #DryRun=True
                    )
                except Exception as e:
                    msg = "Request would have succeeded, but DryRun flag is set."
                    if msg in f"{e}":
                        pass
                    else:
                        raise e

    return


def check_state(instance_id):
    state = None
    resp = client.describe_instance_status(InstanceIds=[instance_id],IncludeAllInstances=True)
    if 'InstanceStatuses' in resp and len(resp['InstanceStatuses']) > 0:
        state = resp['InstanceStatuses'][0]['InstanceState']['Name']
    return state


def wait_until_running(instance_id):
    while True:
        state = check_state(instance_id)
        if state == "running":
            logger.info(f"Instance {instance_id} is now running")
            break
        elif state:
            logger.info(f"Instance {instance_id} is {state}")
        else:
            logger.info(f"Instance {instance_id} state is unknown")
        time.sleep(5)
