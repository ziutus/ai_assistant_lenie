import json
import logging
import boto3
import datetime


# Initialize EC2 client and logger
EC2 = boto3.client('ec2', 'us-east-1')
LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)


def lambda_handler(event, context):
    """
    This function creates an AMI based on provided arguments.
    
    Args:
        event (dict): AWS Lambda event
        event['stage'] (str): Stage
        event['params']['tag'] (str): Tag name to query
        event['params']['tagValue'] (str): Tag value
        event['params']['excludeDevices'] (list): List of devices excluded from AMI
        
    Returns:
        str: AMI id
    """
    stage = event.get('stage')
    tag = event.get('params').get('tag')
    tagValue = event.get('params').get('tagValue')
    excludedDevices = event.get('params').get('excludedDevices')

    class ImageCreationError(Exception):
        pass

    def get_source_instance_details():
        instance_details = {}

        result = EC2.describe_instances(
            Filters=[
                {'Name': 'tag:stage', 'Values': [stage]},
                {'Name': f'tag:{tag}', 'Values': [tagValue]}
            ]
        )
        try:

            source_instance_list = next(iter(result['Reservations']))
            source_instance = next(iter(source_instance_list.get('Instances')))

            instance_details['InstanceId'] = source_instance.get('InstanceId')
            instance_details['BlockDeviceMappings'] = []
            for device in source_instance.get('BlockDeviceMappings'):
                if device['DeviceName'] not in excludedDevices:
                    device_details = {
                        'DeviceName': device['DeviceName'],
                        'Ebs': {
                            'DeleteOnTermination': True,
                            'VolumeType': 'gp3'
                        }
                    }
                else:
                    device_details = {
                        'DeviceName': device['DeviceName'],
                        'NoDevice': ''
                    }
                instance_details['BlockDeviceMappings'].append(device_details)
        except StopIteration:
            LOGGER.error("No instance found")
            raise ImageCreationError("No instance found!")

        return instance_details


    def create_image(source_instance_details):
        source_instance_details['Description'] = tagValue + ' instance backup - ' + str(datetime.datetime.now()).replace(':', '-')
        source_instance_details['Name'] = tagValue + ' instance backup - ' + str(datetime.datetime.now()).replace(":", '-')
        source_instance_details['NoReboot'] = True
        LOGGER.info('Creating AMI for: ' + source_instance_details['InstanceId'])
        
        try:
            response = EC2.create_image(**source_instance_details)
            
            EC2.create_tags(
                Resources=[response.get('ImageId')],
                Tags=[
                    {'Key': 'stage', 'Value': stage }
                    ]
                )
                
            return response.get('ImageId')
        except:
            raise ImageCreationError("Unable to create AMI")


    return(create_image(get_source_instance_details()))