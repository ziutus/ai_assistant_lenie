import json
import logging
import boto3

SSM = boto3.client('ssm', 'us-east-1')
LOGGER = logging.getLogger()
LOGGER.setLevel(logging.info)

class SSMParamUpdateError(Exception): pass


def lambda_handler(event, context):
    """
    Args:
    event.ssmParameters (list) - list of SSM parameter
    """
    
    LOGGER.info('SSM Parameters:' + str(event.get('ssParameters')))


    def set_parameter(name, value):
        try:
            SSM.put_parameter(
                Name = name,
                Value = value,
                Type = 'String',
                Overwrite = True)
            return
        except:
            raise SSmParamUpdateError('Unable to update SSM Parameter')

    for param in event.get('ssmParameters'):
        LOGGER.info('Setting '+ param['ssmParamName'] + ' to ' + param['ssmParamValue'])
        set_parameter(param['ssmParamName'], param['ssmParamValue'])

    return
