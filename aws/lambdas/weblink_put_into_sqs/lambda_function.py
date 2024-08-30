import json
import os
import sys
import boto3
import uuid
from pprint import pprint


def lambda_handler(event, context):
    sqs = boto3.client('sqs')
    s3 = boto3.client('s3')
    queue_url = os.getenv("AWS_QUEUE_URL_ADD")
    bucket_name = "lenie-s3-tmp"

    pprint(event["body"])
    url_data = json.loads(event["body"])

    # Pobierz wartości z url_data
    target_url = url_data.get("url")
    url_type = url_data.get("type")
    source = url_data.get("source", "default_source")
    note = url_data.get("note", "default_note")
    text = url_data.get("text", "")

    # Sprawdź, czy wartości wymagane są obecne
    if not target_url or not url_type:
        error_message = "Missing required parameter(s): 'url' or 'type'"
        print(error_message)
        return {
            'statusCode': 500,
            'body': json.dumps(error_message),
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Credentials': True,
            },
        }

    # Generowanie losowego UID
    uid = str(uuid.uuid4())

    # Tworzenie pliku z wartością zmiennej 'text' i wysyłanie go do S3
    file_name = f"{uid}.txt"
    try:
        s3.put_object(Bucket=bucket_name, Key=file_name, Body=text)
        print(f"Successfully uploaded {file_name} to {bucket_name}")
    except Exception as e:
        error_message = f"Failed to upload {file_name} to {bucket_name}: {str(e)}"
        print(error_message)
        return {
            'statusCode': 500,
            'body': json.dumps(error_message),
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Credentials': True,
            },
        }

    # Utwórz message_body bez 'text'
    message_body = {
        "url": target_url,
        "type": url_type,
        "source": source,
        "note": note,
        "uid": uid  # Dodanie UID do message_body
    }

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

    print("Successfully sent message to SQS, message ID: ", response["MessageId"])

    return {
        'statusCode': 200,
        'body': json.dumps(f'Successfully sent message to SQS, message ID: {response["MessageId"]}'),
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Credentials': True,
            'Access-Control-Allow-Methods': 'OPTIONS,POST,GET'
        },
    }