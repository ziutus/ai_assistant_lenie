import json
import boto3
import os

client = boto3.client("rds")
db_id = os.environ.get('DB_ID')


def lambda_handler(event, context):
    try:
        client.stop_db_instance(DBInstanceIdentifier=db_id)
        return {
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Credentials': True,
                'Access-Control-Allow-Methods': 'OPTIONS,POST,GET'
            },
            'statusCode': 200,
            'body': json.dumps('The database has been started')
        }
    except Exception as e:
        return {
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Credentials': True,
            },
            'statusCode': 500,
            'body': json.dumps(f'Error during stopping database >{db_id} {str(e)}')
        }
