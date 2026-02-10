import json
import datetime
import boto3


class ImageCopyError(Exception): pass

LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)


def lambda_handler(event, context):

    LOGGER.info('AMI Id:' + event.get('amiId'))
    
    tag = event.get('params').get('tag')
    EC2 = boto3.client('ec2', event['drRegion'])
    
    try:
        result = EC2.copy_image(
            Description = tag + ' instance backup - ' + str(datetime.datetime.now()).replace(':', '-'),
            Encrypted = True,
            KmsKeyId = 'alias/aws/ebs',
            Name = tag + ' instance backup - ' + str(datetime.datetime.now()).replace(':', '-'),
            SourceImageId = event['amiId'],
            SourceRegion='us-east-1'
            )

        LOGGER.info('Tagging copie AMI' + result['imageId'])
        
        EC2.create_tags(
            Resources=[result.get('ImageId')],
            Tags=[
                {'Key': 'stage', 'Value': event.get('stage')
                ]
            )
    except:
        raise ImageCopyError("Unable to copy AMI to DR region")

    return
