import pytest
from lambda_functions.palo_alto_failover.src import lambda_function
from lambda_functions.palo_alto_utils.src import utils as global_utils
from unittest.mock import MagicMock

def test_get_palo_instances():
    describe_inst_dict = {
        'Reservations': []
    }
    lambda_function.client = MagicMock(return_value=describe_inst_dict)
    global_utils.get_ssm_param = MagicMock(return_value="test")
    
    with pytest.raises(Exception) as exc_info:
        old_inst, new_inst, vpc_id= lambda_function.get_palo_instances()
    
    assert 'Unable to find VPC ID for instances' in str(exc_info.value)
