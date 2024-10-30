import json
import os

import boto3

client = boto3.client("rds")
db_id = os.environ.get('DB_ID')
#db_id="lenie-dev"

def lambda_handler(event, context):
    try:
        response = client.describe_db_instances(DBInstanceIdentifier=db_id)

        if len(response['DBInstances']) != 1:
            return {
            'headers': {
                  'Access-Control-Allow-Origin': '*',
                  'Access-Control-Allow-Credentials': True,
                },
                'statusCode': 500,
                'body': json.dumps(f'Error during checking status of database, wrong number of DB instances! >{len(response["DBInstances"])}')
            }

        return {
            'statusCode': 200,
            'body': response['DBInstances'][0]['DBInstanceStatus'],
            'headers': {
                  'Access-Control-Allow-Origin': '*',
                  'Access-Control-Allow-Credentials': True,
                  'Access-Control-Allow-Methods': 'OPTIONS,POST,GET'
            },
        }

    except Exception as e:
        pass
        return {
            'headers': {
                  'Access-Control-Allow-Origin': '*',
                  'Access-Control-Allow-Credentials': True,
            },
            'statusCode': 500,
            'body': json.dumps(f'Error during checking status of database >{db_id} {str(e)}')
        }
