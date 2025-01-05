import json
import os

import boto3
from dotenv import load_dotenv

from library.stalker_web_document import StalkerDocumentStatus, StalkerDocumentType, \
    StalkerDocumentStatusError
# Importacja własnych modułów
from library.stalker_web_document_db import StalkerWebDocumentDB
from library.stalker_web_documents_db_postgresql import WebsitesDBPostgreSQL
from library.website.website_download_context import download_raw_html, webpage_raw_parse

# Ładowanie zmiennych środowiskowych
load_dotenv()

aws_xray_enabled = os.getenv("AWS_XRAY_ENABLED")
print(f"aws_xray_enabled: {aws_xray_enabled}")

if aws_xray_enabled:
    from aws_xray_sdk.core import xray_recorder, patch_all
    from aws_xray_sdk.core import patch

    # Konfiguracja X-Ray
    xray_recorder.configure(service='lenie_ai')
    patch_all()  # Automatyczne łatanie wszystkich bibliotek

if __name__ == '__main__':
    if aws_xray_enabled:
        xray_recorder.begin_segment('MainSegment')  # Rozpoczęcie głównego segmentu

    model = os.getenv("EMBEDDING_MODEL")
    s3_bucket = os.getenv("AWS_S3_WEBSITE_CONTENT")
    print(f"Using >{model}< for embedding")

    if not s3_bucket:
        print("The S3 bucket for text files is not set, exiting.")
        exit(1)

    print("AWS REGION: ", os.getenv("AWS_REGION"))
    queue_url = os.getenv("AWS_QUEUE_URL_ADD")

    print("Step 1: Taking pages to put into RDS database")
    boto_session = boto3.session.Session(
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        region_name=os.getenv("AWS_REGION")
    )

    # Łatanie klienta boto3
    if aws_xray_enabled:
        patch(['boto3'])

    sqs = boto_session.client('sqs')

    while True:
        response = sqs.receive_message(
            QueueUrl=queue_url,
            AttributeNames=['All'],
            MaxNumberOfMessages=10,
        )

        if 'Messages' not in response:
            print('No messages in queue')
            break

        for message in response['Messages']:
            if aws_xray_enabled:
                xray_recorder.begin_subsegment('ProcessMessage')  # Rozpoczęcie podsegmentu
            try:
                print('Message: ', message['Body'])

                link_data = json.loads(message['Body'])
                if "source" not in link_data:
                    link_data["source"] = "own"

                print("Link Data:  URL", link_data["url"], "type:", link_data["type"], " source:", link_data["source"],
                      "note:", link_data['note'])
                if 'chapterList' in link_data:
                    print(link_data["chapterList"])

                web_doc = StalkerWebDocumentDB(link_data["url"])
                if web_doc.id:
                    print("This Url exist in, ignoring ")
                    sqs.delete_message(
                        QueueUrl=queue_url,
                        ReceiptHandle=message['ReceiptHandle']
                    )
                    continue

                print("DEBUG: Adding Web Document", end=" ")
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

                id_added = web_doc.save()
                print(f"Added to database with ID {id_added}")
                print("[DONE]")

                sqs.delete_message(
                    QueueUrl=queue_url,
                    ReceiptHandle=message['ReceiptHandle']
                )
            except Exception as e:
                print(f'An error occurred: {e}')
            finally:
                if aws_xray_enabled:
                    xray_recorder.end_subsegment()  # Koniec podsegmentu

    print("Step 2: Downloading websites (or taking from S3) and putting data into database")
    websites = WebsitesDBPostgreSQL()
    website_data = websites.get_ready_for_download()
    websites_data_len = len(website_data)
    print(f"Number of pages and links to download: {websites_data_len}")

    s3 = boto_session.client('s3')

    website_nb = 1
    for page_info in website_data:
        website_id = int(page_info[0])
        url = page_info[1]
        website_document_type = page_info[2]
        s3_uuid = page_info[3]
        progress = round((website_nb / websites_data_len) * 100)

        print(f"Processing >{website_document_type}< {website_id} ({website_nb} from {websites_data_len} {progress}%):"
              f" {url}")

        if aws_xray_enabled:
            xray_recorder.begin_subsegment('ProcessPage')  # Rozpoczęcie podsegmentu
        try:
            if website_document_type not in ["webpage", "link"]:
                print(f"Document type is not webpage or link: {website_document_type}, ignoring")
                continue

            if website_document_type == "webpage" and s3_uuid:
                try:
                    print(f"* Reading text of article from S3 bucket >{s3_bucket}< and file: >{s3_uuid}.txt<", end=" ")
                    obj = s3.get_object(Bucket=s3_bucket, Key=f"{s3_uuid}.txt")
                    content = obj['Body'].read().decode('utf-8')
                    web_doc = StalkerWebDocumentDB(url)
                    web_doc.text = content
                    print('[DONE]')

                    web_doc.analyze()
                    web_doc.validate()

                    print(
                        "* ALL DONE, updating state to NEED_MANUAL_REVIEW (cleaning of text is needed) as it is >webpage<",
                        end=" ")
                    web_doc.document_state = StalkerDocumentStatus.NEED_MANUAL_REVIEW
                    print("[DONE]")
                    web_doc.save()

                except Exception as e:
                    print(f'An error occurred: {e}')
                    exit(1)
            else:
                try:
                    print("* Downloading raw html from remote webpage", end=" ")
                    raw_html = download_raw_html(url)
                    if not raw_html:
                        print("empty response! [ERROR]")
                        web_doc = StalkerWebDocumentDB(url)
                        web_doc.document_state = StalkerDocumentStatus.ERROR
                        web_doc.document_state_error = StalkerDocumentStatusError.ERROR_DOWNLOAD
                        web_doc.save()
                        continue

                    print(round(len(raw_html) / 1024, 2), end="KB ")
                    print('[DONE]')

                    parse_result = webpage_raw_parse(url, raw_html)

                    web_doc = StalkerWebDocumentDB(url, webpage_parse_result=parse_result)
                    print(f"DEBUG: url:{web_doc.url}")

                    web_doc.analyze()
                    web_doc.validate()
                    web_doc.save()

                except Exception as e:
                    print(f"Error processing website {website_id}: {url}")
                    print(str(e))
                    exit(1)

                if web_doc.document_type == StalkerDocumentType.webpage:
                    print(
                        "* ALL DONE, updating state to NEED_MANUAL_REVIEW (cleaning of text is needed) as it is >webpage<",
                        end=" ")
                    web_doc.document_state = StalkerDocumentStatus.NEED_MANUAL_REVIEW
                    print("[DONE]")
                    web_doc.save()
        finally:
            if aws_xray_enabled:
                xray_recorder.end_subsegment()  # Koniec podsegmentu

        website_nb += 1

    print("Step 3: For youtube video setup status ready for translation if transcription is done")
    transcirption_done = websites.get_transcription_done()
    transcirption_done_len = len(transcirption_done)
    website_nb = 1
    print(f"entries to correct: {transcirption_done_len}")
    for website_id in transcirption_done:
        progress = round((website_nb / transcirption_done_len) * 100)
        web_doc = StalkerWebDocumentDB(document_id=website_id)
        print(f"Processing  {web_doc.id} {web_doc.document_type.name} ({website_nb} from {websites_data_len} "
              f"{progress}%): "
              f"{web_doc.url}")
        web_doc.document_state = StalkerDocumentStatus.READY_FOR_TRANSLATION
        web_doc.save()
        website_nb += 1

    print("Step 4: TRANSLATION")
    translation_needed = websites.get_ready_for_translation()
    websites_data_len = len(translation_needed)
    print(f"entries to translation: {websites_data_len}")
    website_nb = 1
    for website_id in translation_needed:
        web_doc = StalkerWebDocumentDB(document_id=website_id)

        progress = round((website_nb / websites_data_len) * 100)

        print(f"Processing  {web_doc.id} {web_doc.document_type.name} ({website_nb} from {websites_data_len} "
              f"{progress}%): "
              f"{web_doc.url}")
        web_doc.translate_to_english()
        web_doc.save()
        website_nb += 1

    print("Step 5: adding embedding")
    embedding_needed = websites.get_ready_for_embedding()
    website_nb = 1
    embedding_needed_len = len(embedding_needed)
    print(f"entries to analyze: {embedding_needed_len}")
    for website_id in embedding_needed:
        web_doc = StalkerWebDocumentDB(document_id=website_id)

        progress = round((website_nb / embedding_needed_len) * 100)
        print(f"Working on ID:{web_doc.id} ({website_nb} from {embedding_needed_len} {progress}%)"
              f" {web_doc.document_type}" f"url: {web_doc.url}")
        website_nb += 1

        web_doc.embedding_add(model=model)
        web_doc.save()

    if aws_xray_enabled:
        xray_recorder.end_segment()  # Koniec głównego segmentu
