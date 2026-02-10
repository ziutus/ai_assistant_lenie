import json
import boto3
import logging

EC2 = boto3.client('ec2', 'us-east-1')
LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)


def lambda_handler(event, context):
    """
    Args event.amiId(str) - AMI to get status
    
    Returns:
      str: AMI status 
    """
    LOGGER.info('AMI Id:' + event.get('amiId'))
    
    def get_image_state(amiId):
        result = EC2.describe_images(imageIds=[amiId])
        try:
            image = next(iter(result['Images']))
            LOGGER.info(amiId + ' is ' + image.get('State'))
            return image.get('State')
        except StopIteration:
            raise Exception('AMI ' + amiId + ' not found')

    
    return(get_image_state(event.get('amiId')))