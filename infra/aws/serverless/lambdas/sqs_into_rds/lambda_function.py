import json
import boto3
import os
from library.stalker_web_document_db import StalkerWebDocumentDB
import os
import logging
from pprint import pprint

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

sqs = boto3.client('sqs')

def lambda_handler(event, context):
    queue_url = os.getenv("AWS_QUEUE_URL_ADD")

    logger.info(event)
    print(type(event))
    message = event

    # try:
    link_data = event["Body"]
    pprint(link_data)

    if "source" not in link_data:
        link_data["source"] = "own"

    web_doc = StalkerWebDocumentDB(link_data["url"])
    if web_doc.id:
        print(f"This Url exist in with {web_doc.id}, ignoring ")
        sqs.delete_message(
            QueueUrl=queue_url,
            ReceiptHandle=message['ReceiptHandle']
        )
        print("Message deleted from SQS queue")
        return {
            'statusCode': 200,
            'body': json.dumps(message['ReceiptHandle'])
        }

    # logger.info("Adding Web Document")
    web_doc.set_document_type(link_data["type"])
    web_doc.source = link_data["source"]
    if 'chapterList' in link_data:
        web_doc.chapter_list = link_data["chapterList"]
    if 'language' in link_data:
        web_doc.language = link_data["language"]
    if 'makeAISummary' in link_data:
        web_doc.ai_summary_needed = link_data["makeAISummary"]
    if 'note' in link_data:
        web_doc.note = link_data["note"]
    if 's3_uuid' in link_data:
        web_doc.s3_uuid = link_data["s3_uuid"]
    if 'title' in link_data:
        web_doc.title = link_data["title"]
    if 'paywall' in link_data:
        web_doc.paywall = link_data["paywall"]
    if 'ai_summary' in link_data:
        web_doc.ai_summary = link_data["ai_summary"]
    if 'ai_correction' in link_data:
        web_doc.ai_correction = link_data["ai_correction"]
    if 'chapter_list' in link_data:
        web_doc.chapter_list = link_data["chapter_list"]
    if 'source' in link_data:
        web_doc.source = link_data["source"]

    id_added = web_doc.save()
    # print(f"Added to database with ID {id_added}")

    sqs.delete_message(
        QueueUrl=queue_url,
        ReceiptHandle=message['ReceiptHandle']
    )
    # except Exception as e:
    #     print(f'An error occurred: {e}')

    # TODO implement
    return {
        'statusCode': 200,
        'body': json.dumps('Hello from Lambda!')
    }
