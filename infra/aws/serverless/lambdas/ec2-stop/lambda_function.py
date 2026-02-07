import boto3
import os
import json


def lambda_handler(event, context):
    ec2 = boto3.client('ec2')
    instance_id = os.environ.get('INSTANCE_ID')

    if not instance_id:
        return {
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Credentials': True,
            },
            'statusCode': 400,
            'body': json.dumps('INSTANCE_ID environment variable is not set')
        }

    try:
        ec2.stop_instances(InstanceIds=[instance_id])
        print(f'Successfully stopped instance {instance_id}')
        return {
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Credentials': True,
            },
            'statusCode': 200,
            'body': json.dumps(f'Successfully stopped instance {instance_id}'),
        }
    except Exception as e:
        print(f'Error stopping instance {instance_id}: {str(e)}')
        return {
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Credentials': True,
            },
            'statusCode': 500,
            'body': json.dumps(f'Error stopping instance {instance_id}: {str(e)}')
        }
