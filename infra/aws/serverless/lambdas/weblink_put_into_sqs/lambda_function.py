import json
import os
import boto3
import uuid

import logging

logger = logging.getLogger()
logger.setLevel("INFO")


# https://docs.aws.amazon.com/lambda/latest/dg/python-logging.html

def lambda_handler(event, context):

    queue_url = os.getenv("AWS_QUEUE_URL_ADD")
    bucket_name = os.getenv("BUCKET_NAME")

    if bucket_name is None:
        error_message = "BUCKET_NAME environment variable is not set"
        logger.error(error_message)
        return {
            'statusCode': 500,
            'body': json.dumps(error_message),
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Credentials': True,
            },
        }

    if queue_url is None:
        error_message = "AWS_QUEUE_URL_ADD environment variable is not set"
        logger.error(error_message)
        return {
            'statusCode': 500,
            'body': json.dumps(error_message),
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Credentials': True,
            },
        }

    sqs = boto3.client('sqs')
    s3 = boto3.client('s3')

    url_data = json.loads(event["body"])
    url_data_print = json.loads(event["body"])
    url_data_print["text"] = url_data_print["text"][:50]
    url_data_print["html"] = url_data_print["html"][:50]

    logger.info('data which came by API gateway', extra=url_data_print)

    target_url = url_data.get("url")
    url_type = url_data.get("type")
    note = url_data.get("note", "default_note")
    text = url_data.get("text", "")
    html = url_data.get("html", "")
    title = url_data.get("title", "")
    language = url_data.get("language", "")
    paywall = url_data.get("paywall", False)
    source = url_data.get("source", "own")
    ai_summary = url_data.get("ai_summary", False)
    ai_correction = url_data.get("ai_correction", False)
    chapter_list = url_data.get("chapter_list", False)

    if not target_url or not url_type:
        error_message = "Missing required parameter(s): 'url' or 'type'"
        logger.error(error_message)
        return {
            'statusCode': 500,
            'body': json.dumps(error_message),
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Credentials': True,
            },
        }

    if url_type == 'webpage':
        uid = str(uuid.uuid4())

        file_name = f"{uid}.txt"
        try:
            s3.put_object(Bucket=bucket_name, Key=file_name, Body=text)
            logger.info(f"Successfully uploaded {file_name} to {bucket_name}")
        except Exception as e:
            error_message = f"Failed to upload {file_name} to {bucket_name}: {str(e)}"
            logger.error(error_message)
            return {
                'statusCode': 500,
                'body': json.dumps(error_message),
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Credentials': True,
                },
            }

        if not html:
            logger.info("Missing HTML part!")
        else:
            file_name = f"{uid}.html"
            try:
                s3.put_object(Bucket=bucket_name, Key=file_name, Body=html)
                logger.info(f"Successfully uploaded {file_name} to {bucket_name}")
            except Exception as e:
                error_message = f"Failed to upload {file_name} to {bucket_name}: {str(e)}"
                logger.error(error_message)
                return {
                    'statusCode': 500,
                    'body': json.dumps(error_message),
                    'headers': {
                        'Access-Control-Allow-Origin': '*',
                        'Access-Control-Allow-Credentials': True,
                    },
                }

        message_body = {
            "url": target_url,
            "type": "webpage",
            "source": source,
            "note": note,
            "title": title,
            "language": language,
            "paywall": paywall,
            "ai_summary": ai_summary,
            "ai_correction": ai_correction,
            "chapter_list": chapter_list,
            "s3_uuid": uid
        }
    else:
        message_body = {
            "url": target_url,
            "type": url_type,
            "source": source,
            "note": note,
            "title": title,
            "language": language,
            "paywall": paywall,
            "ai_summary": ai_summary,
            "ai_correction": ai_correction,
            "chapter_list": chapter_list,
        }

    response = sqs.send_message(
        QueueUrl=queue_url,
        DelaySeconds=10,
        MessageBody=json.dumps(message_body)
    )

    if response["ResponseMetadata"]['HTTPStatusCode'] != 200:
        logger.error("Failed to send message to SQS")
        return {
            'statusCode': 500,
            'body': json.dumps("Failed to send message to SQS"),
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Credentials': True,
            },
        }

    logger.info(f"Successfully sent message to SQS, message ID: {response['MessageId']}")

    return {
        'statusCode': 200,
        'body': json.dumps(f'Successfully sent message to SQS, message ID: {response["MessageId"]}'),
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Credentials': True,
            'Access-Control-Allow-Methods': 'OPTIONS,POST,GET'
        },
    }
