import boto3
import os
import json

client = boto3.client('rds')
db_id = os.environ.get('DB_ID')

HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Credentials': True,
}


def lambda_handler(event, context):
    if not db_id:
        return {
            'headers': HEADERS,
            'statusCode': 400,
            'body': json.dumps('DB_ID environment variable is not set')
        }

    resource = event.get('resource', '')
    action = resource.split('/')[-1]  # 'start', 'stop', or 'status'

    try:
        if action == 'start':
            client.start_db_instance(DBInstanceIdentifier=db_id)
            body = f'Successfully started database {db_id}'
        elif action == 'stop':
            client.stop_db_instance(DBInstanceIdentifier=db_id)
            body = f'Successfully stopped database {db_id}'
        elif action == 'status':
            response = client.describe_db_instances(DBInstanceIdentifier=db_id)
            if len(response['DBInstances']) != 1:
                return {
                    'headers': HEADERS,
                    'statusCode': 500,
                    'body': json.dumps(f'Wrong number of DB instances: {len(response["DBInstances"])}')
                }
            body = response['DBInstances'][0]['DBInstanceStatus']
        else:
            return {
                'headers': HEADERS,
                'statusCode': 400,
                'body': json.dumps(f'Unknown action: {action}')
            }

        print(f'RDS {action} for {db_id}: {body}')
        return {
            'headers': HEADERS,
            'statusCode': 200,
            'body': json.dumps(body),
        }
    except Exception as e:
        print(f'Error during RDS {action} for {db_id}: {str(e)}')
        return {
            'headers': HEADERS,
            'statusCode': 500,
            'body': json.dumps(f'Error during RDS {action} for {db_id}: {str(e)}')
        }
