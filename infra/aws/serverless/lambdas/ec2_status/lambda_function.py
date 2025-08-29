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
        response = ec2.describe_instances(InstanceIds=[instance_id])
        state = response['Reservations'][0]['Instances'][0]['State']['Name']
        print(f'Instance {instance_id} is {state}')
        return {
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Credentials': True,
            },
            'statusCode': 200,
            'body': json.dumps(f'{state}'),
        }
    except Exception as e:
        print(f'Error checking status of instance {instance_id}: {str(e)}')
        return {
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Credentials': True,
            },
            'statusCode': 500,
            'body': json.dumps(f'Error checking status of instance {instance_id}: {str(e)}')
        }
