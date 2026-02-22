import boto3
import os
import json

ec2 = boto3.client('ec2')
instance_id = os.environ.get('INSTANCE_ID')

HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Credentials': True,
}


def lambda_handler(event, context):
    if not instance_id:
        return {
            'headers': HEADERS,
            'statusCode': 400,
            'body': json.dumps('INSTANCE_ID environment variable is not set')
        }

    resource = event.get('resource', '')
    action = resource.split('/')[-1]  # 'start', 'stop', or 'status'

    try:
        if action == 'start':
            ec2.start_instances(InstanceIds=[instance_id])
            body = f'Successfully started instance {instance_id}'
        elif action == 'stop':
            ec2.stop_instances(InstanceIds=[instance_id])
            body = f'Successfully stopped instance {instance_id}'
        elif action == 'status':
            response = ec2.describe_instances(InstanceIds=[instance_id])
            body = response['Reservations'][0]['Instances'][0]['State']['Name']
        else:
            return {
                'headers': HEADERS,
                'statusCode': 400,
                'body': json.dumps(f'Unknown action: {action}')
            }

        print(f'EC2 {action} for {instance_id}: {body}')
        return {
            'headers': HEADERS,
            'statusCode': 200,
            'body': json.dumps(body),
        }
    except Exception as e:
        print(f'Error during EC2 {action} for {instance_id}: {str(e)}')
        return {
            'headers': HEADERS,
            'statusCode': 500,
            'body': json.dumps(f'Error during EC2 {action} for {instance_id}: {str(e)}')
        }
