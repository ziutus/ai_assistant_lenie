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

def lambda_handler(event, context):

    logger.info(event)
    print(type(event))
    message = event

    # try:
    link_data = json.loads(event["Body"])
    pprint(link_data)

    if "source" not in link_data:
        link_data["source"] = "own"

    web_doc = StalkerWebDocumentDB(link_data["url"])
    if web_doc.id:
        print(f"This Url exist in with {web_doc.id}, ignoring ")
        print("Message should be now deleted from SQS queue")
        return {
            'statusCode': 200,
            'body': message['ReceiptHandle']
        }

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

    # TODO implement
    return {
        'statusCode': 200,
        'body': message['ReceiptHandle']
    }
