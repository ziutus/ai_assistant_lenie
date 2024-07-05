import json
import os
import sys
import boto3
from pprint import pprint


def lambda_handler(event, context):
    # TODO implement
    sqs = boto3.client('sqs')
    queue_url = os.getenv("AWS_QUEUE_URL_ADD")

    # pprint(event)
    # target_url = event['url']
    # url_type = event['type']

    pprint(event["body"])
    url_data = json.loads(event["body"])
    target_url = url_data["url"]
    url_type = url_data["type"]
    source = url_data["source"]

    message_body = {"url": target_url, "type": url_type, "source": source}

    response = sqs.send_message(
        QueueUrl=queue_url,
        DelaySeconds=10,
        MessageBody=json.dumps(message_body)
    )

    if response["ResponseMetadata"]['HTTPStatusCode'] != 200:
        print("Failed to send message to SQS")
        return {
            'statusCode': 500,
            'body': json.dumps("Failed to send message to SQS"),
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Credentials': True,
            },
        }

    print("Successfully sent message to SQS, messeage got ID: ", response["MessageId"])

    return {
        'statusCode': 200,
        'body': json.dumps(f'Successfully sent message to SQS, messeage got ID: {response["MessageId"]}'),
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Credentials': True,
            'Access-Control-Allow-Methods': 'OPTIONS,POST,GET'
        },
    }
