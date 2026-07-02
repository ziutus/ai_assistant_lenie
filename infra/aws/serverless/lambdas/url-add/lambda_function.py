import json
import os
import boto3
import uuid
from datetime import datetime

import logging

logger = logging.getLogger()
logger.setLevel("INFO")


# https://docs.aws.amazon.com/lambda/latest/dg/python-logging.html

def _error_response(message: str, status_code: int = 500):
    logger.error(message)
    return {
        'statusCode': status_code,
        'body': json.dumps(message),
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Credentials': True,
        },
    }


def lambda_handler(event, context):

    bucket_name = os.getenv("BUCKET_NAME")
    dynamodb_table_name = os.getenv("DYNAMODB_TABLE_NAME", "lenie_dev_documents")

    if bucket_name is None:
        return _error_response("BUCKET_NAME environment variable is not set")

    s3 = boto3.client('s3')
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(dynamodb_table_name)

    url_data = json.loads(event["body"]) if isinstance(event["body"], str) else event["body"]
    url_data_print = json.loads(event["body"]) if isinstance(event["body"], str) else event["body"]

    url_data_print["text"] = url_data_print["text"][:50]
    url_data_print["html"] = url_data_print["html"][:50]

    logger.info('data which came by API gateway', extra={"body": url_data_print})

    target_url = url_data.get("url")
    url_type = url_data.get("type")
    note = url_data.get("note", "default_note")
    text = url_data.get("text", "")
    html = url_data.get("html", "")
    title = url_data.get("title", "")
    language = url_data.get("language", "")
    paywall = url_data.get("paywall", False)
    source = url_data.get("source", "own")
    chapter_list = url_data.get("chapter_list", False)

    if not target_url or not url_type:
        return _error_response("Missing required parameter(s): 'url' or 'type'")

    # Generuj unikalny identyfikator i timestamp
    uid = str(uuid.uuid4())
    timestamp = datetime.utcnow().isoformat()
    created_date = timestamp[:10]  # YYYY-MM-DD

    if url_type == 'webpage':

        file_name = f"{uid}.txt"
        try:
            s3.put_object(Bucket=bucket_name, Key=file_name, Body=text)
            logger.info(f"Successfully uploaded {file_name} to {bucket_name}")
        except Exception as e:
            return _error_response(f"Failed to upload {file_name} to {bucket_name}: {str(e)}")

        if not html:
            logger.info("Missing HTML part!")
        else:
            file_name = f"{uid}.html"
            try:
                s3.put_object(Bucket=bucket_name, Key=file_name, Body=html)
                logger.info(f"Successfully uploaded {file_name} to {bucket_name}")
            except Exception as e:
                return _error_response(f"Failed to upload {file_name} to {bucket_name}: {str(e)}")

    # Zapis do DynamoDB jest krytyczny — to jedyny magazyn metadanych dokumentu
    # (kolejka SQS i jej konsument SQS->RDS zostały usunięte 2026-07-02).
    try:
        dynamodb_item = {
            'pk': 'DOCUMENT',
            'sk': f"{timestamp}#{uid}",
            'document_id': uid,
            'url': target_url,
            'type': url_type,
            'source': source,
            'note': note,
            'title': title,
            'language': language,
            'paywall': paywall,
            'chapter_list': chapter_list,
            'created_at': timestamp,
            'created_date': created_date,
        }

        # Dodaj s3_uuid tylko dla webpage
        if url_type == 'webpage':
            dynamodb_item['s3_uuid'] = uid

        table.put_item(Item=dynamodb_item)
        logger.info(f"Successfully saved document to DynamoDB: {uid}")
    except Exception as e:
        return _error_response(f"Failed to save to DynamoDB: {str(e)}")

    return {
        'statusCode': 200,
        'body': json.dumps(f'Successfully saved document, id: {uid}'),
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Credentials': True,
            'Access-Control-Allow-Methods': 'OPTIONS,POST,GET'
        },
    }
