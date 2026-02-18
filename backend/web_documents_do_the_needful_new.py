import json
import logging
import os
import uuid

from markitdown import MarkItDown
import boto3
from dotenv import load_dotenv

# Importacja własnych modułów
from library.website.website_download_context import download_raw_html, webpage_raw_parse, webpage_text_clean

from library.stalker_web_document import StalkerDocumentStatus, StalkerDocumentType, StalkerDocumentStatusError
from library.stalker_web_document_db import StalkerWebDocumentDB
from library.stalker_web_documents_db_postgresql import WebsitesDBPostgreSQL
from library.embedding import embedding_need_translation
from library.youtube_processing import process_youtube_url

# Ładowanie zmiennych środowiskowych
load_dotenv()

logging.basicConfig(level=logging.INFO)  # Change level as per your need

aws_xray_enabled = os.getenv("AWS_XRAY_ENABLED")
print(f"aws_xray_enabled: {aws_xray_enabled}")



"""
TODO: add limits for asemblay.ai upload files (check), see: https://www.assemblyai.com/docs/concepts/faq
Currently, the maximum file size that can be submitted to the /v2/transcript endpoint for transcription is 5GB,
and the maximum duration is 10 hours.
The maximum file size for a local file uploaded to the API via the /v2/upload endpoint is 2.2GB.
"""

if __name__ == '__main__':

    # model = os.getenv("EMBEDDING_MODEL")
    embedding_model = os.getenv("EMBEDDING_MODEL")
    cache_dir = os.getenv("CACHE_DIR")
    s3_bucket = os.getenv("AWS_S3_WEBSITE_CONTENT")
    s3_bucket_transcript = os.getenv("AWS_S3_TRANSCRIPT")
    transcript_provider = os.getenv("TRANSCRIPT_PROVIDER")
    llm_model = os.getenv("AI_MODEL_SUMMARY")
    interactive: bool = False

    print(f"Using >{embedding_model}< for embedding")

    if not s3_bucket:
        print("The S3 bucket for text and html files is not set, exiting.")
        exit(1)

    if not s3_bucket_transcript:
        print("The S3 bucket for stranscript files is not set, exiting.")
        exit(1)

    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir)

    print("AWS REGION: ", os.getenv("AWS_REGION"))
    queue_url = os.getenv("AWS_QUEUE_URL_ADD")

    print("Step 1: Taking pages to put into RDS database")
    boto_session = boto3.session.Session(
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        region_name=os.getenv("AWS_REGION")
    )

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
                print(f"Added to database with ID {id_added}")
                print("[DONE]")

                sqs.delete_message(
                    QueueUrl=queue_url,
                    ReceiptHandle=message['ReceiptHandle']
                )
            except Exception as e:
                print(f'An error occurred: {e}')

    websites = WebsitesDBPostgreSQL()

    print("Step 2 a: putting youtube movies data into database")
    website_data = websites.get_youtube_just_added()
    logging.info(f"Entries to analyze: {len(website_data)}")
    for movie in website_data:
        logging.info(f"Working on document ID: {movie[0]}")
        try:
            web_document = StalkerWebDocumentDB(document_id=int(movie[0]))
            process_youtube_url(
                youtube_url=web_document.url,
                language=web_document.language,
                chapter_list=web_document.chapter_list,
                ai_summary_needed=web_document.ai_summary_needed,
                cache_dir=cache_dir,
                transcript_provider=transcript_provider,
                llm_model=llm_model,
            )
        except Exception as e:
            logging.error(f"Error processing document {movie[0]}: {e}")

    print("Step 2 b: Downloading websites (or taking from S3) and putting data into database")
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

                    print(f"* Reading text of article from S3 bucket >{s3_bucket}< and file: >{s3_uuid}.html<", end=" ")
                    obj = s3.get_object(Bucket=s3_bucket, Key=f"{s3_uuid}.html")
                    content = obj['Body'].read().decode('utf-8')

                    page_file = f"tmp/{s3_uuid}.html"
                    with open(f"{page_file}", 'w', encoding="utf-8") as file:
                        file.write(content)

                    md = MarkItDown()
                    result = md.convert(page_file)

                    md_file = f"tmp/{s3_uuid}.md"
                    with open(f"{md_file}", 'w', encoding="utf-8") as file:
                        file.write(result.text_content)

                    md_clean_file = f"tmp/{s3_uuid}_clean.md"
                    md_cleaned = result.text_content

                    md_cleaned = webpage_text_clean(url, md_cleaned)

                    # md_cleaned = remove_before_regex(md_cleaned, r"min czytania")
                    # md_cleaned = remove_before_regex(md_cleaned, r"Lubię to")
                    # md_cleaned = remove_last_occurrence_and_after(md_cleaned,
                    #                                               r"\*Dziękujemy, że przeczytałaś/eś nasz artykuł do końca.")
                    #
                    # md_cleaned = remove_matching_lines(md_cleaned)

                    web_doc.text_md = md_cleaned

                    with open(f"{md_clean_file}", 'w', encoding="utf-8") as file:
                        file.write(md_cleaned)

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

                    if web_doc.document_state == StalkerDocumentStatus.URL_ADDED and web_doc.document_type == StalkerDocumentType.link:
                        web_doc.document_state = StalkerDocumentStatus.READY_FOR_TRANSLATION

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
            print(".")

        website_nb += 1

    print("Step 3: Making correction of text and markdown entries")
    markdown_correction_needed = websites.get_list(document_state='NEED_CLEAN_MD')
    markdown_correction_needed_len = len(markdown_correction_needed)
    document_nb = 1
    print(f"entries to correct: {markdown_correction_needed_len}")
    for document in markdown_correction_needed:
        progress = round((document_nb / markdown_correction_needed_len) * 100)
        web_doc = StalkerWebDocumentDB(document_id=document['id'])
        print(
            f"Processing  {web_doc.id} {web_doc.document_type.name} ({document_nb} from {markdown_correction_needed_len} "
            f"{progress}%): "
            f"{web_doc.url}")
        web_doc.text_md = webpage_text_clean(web_doc.url, web_doc.text_md)
        web_doc.document_state = StalkerDocumentStatus.NEED_MANUAL_REVIEW
        web_doc.save()

    print("Step 4: For youtube video setup status ready for translation if transcription is done")
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

    print("Step 5: TRANSLATION")
    translation_needed = websites.get_ready_for_translation()
    websites_data_len = len(translation_needed)
    print(f"entries to translation: {websites_data_len}")
    website_nb = 1
    for website_id in translation_needed:
        web_doc = StalkerWebDocumentDB(document_id=website_id)

        progress = round((website_nb / websites_data_len) * 100)

        if embedding_need_translation(model=embedding_model):
            raise("Need translation implemented back")
            # print(f"Processing  {web_doc.id} {web_doc.document_type.name} ({website_nb} from {websites_data_len} "
            #       f"{progress}%): "
            #       f"{web_doc.url}")
            # web_doc.translate_to_english()
        else:
            web_doc.set_document_state("READY_FOR_EMBEDDING")
        web_doc.save()
        website_nb += 1

    print("Step 6: making AI tekst correction")
    ai_correction_needed = websites.get_list(ai_correction_needed=True)
    # pprint(ai_correction_needed)

    print("Step 7: making AI tekst summary")
    ai_summary_needed = websites.get_list(ai_summary_needed=True)
    # pprint(ai_summary_needed)

    # print("Step 8: adding embedding")
    # embedding_needed = websites.get_ready_for_embedding()
    # website_nb = 1
    # embedding_needed_len = len(embedding_needed)
    # print(f"entries to analyze: {embedding_needed_len}")
    # for website_id in embedding_needed:
    #     web_doc = StalkerWebDocumentDB(document_id=website_id)
    #
    #     progress = round((website_nb / embedding_needed_len) * 100)
    #     print(f"Working on ID:{web_doc.id} ({website_nb} from {embedding_needed_len} {progress}%)"
    #           f" {web_doc.document_type}" f"url: {web_doc.url}")
    #     website_nb += 1
    #     web_doc.embedding_add(model=embedding_model)
    #     web_doc.save()

    print("Step 9: adding missing markdown entries")
    # TODO: sprawdzić, dlaczego jest problem z pobraniem poniższych stron
    problems = [38, 89, 150, 157, 191, 208, 220, 311, 371, 376, 396,
                443, 456, 465, 470, 486, 497, 499, 503, 531, 553, 581, 592, 600, 601, 602, 611, 662,
                664, 668, 686, 694, 1013, 6735, 6863, 6878, 6883, 6904, 6913, 6918, 6923, 6926, 6930, 7025]

    # 611 certificate expired
    # problems = []

    document_id_start = max(problems) if len(problems) > 0 else 0
    md_needed = websites.get_documents_md_needed(min=document_id_start)
    print(md_needed)

    s3 = boto3.client('s3')

    for document_id in md_needed:
        web_doc = StalkerWebDocumentDB(document_id=document_id)

        if web_doc.paywall:
            print("Need manual download")
            continue

        if web_doc.id in problems:
            print(f"Skipping problem on {document_id}")
            continue

        print(f"Downloading {web_doc.id} {web_doc.url}, md len({len(web_doc.text_md)})")

        html = download_raw_html(url=web_doc.url)
        if not html:
            print("empty response! [ERROR]")
            web_doc.document_state = StalkerDocumentStatus.ERROR
            web_doc.document_state_error = StalkerDocumentStatusError.ERROR_DOWNLOAD
            web_doc.save()
            continue

            # Detect encoding and handle invalid bytes
        try:
            html = html.decode("utf-8")
        except UnicodeDecodeError:
            import chardet

            detected_encoding = chardet.detect(html)['encoding']
            print(f"Detected encoding: {detected_encoding}")
            if detected_encoding:
                html = html.decode(detected_encoding, errors="replace")
            else:
                print("Encoding detection failed, using replacement characters.")
                html = html.decode("latin-1", errors="replace")

        s3_uuid = str(uuid.uuid4())
        file_name = f"{s3_uuid}.html"

        try:
            s3.put_object(Bucket=s3_bucket, Key=file_name, Body=html)
            print(f"Successfully uploaded {file_name} to {s3_bucket}")
        except Exception as e:
            error_message = f"Failed to upload {file_name} to {s3_bucket}: {str(e)}"
            print(error_message)
            exit(1)

        page_file = f"tmp/{s3_uuid}.html"
        with open(f"{page_file}", 'w', encoding="utf-8") as file:
            file.write(html)

        md = MarkItDown()
        result = md.convert(page_file)

        md_file = f"tmp/{s3_uuid}.md"
        with open(f"{md_file}", 'w', encoding="utf-8") as file:
            file.write(result.text_content)

        md_clean_file = f"tmp/{s3_uuid}_clean.md"
        md_cleaned = result.text_content

        # md_cleaned = webpage_text_clean(web_doc.url, md_cleaned)
        web_doc.text_md = md_cleaned
        web_doc.s3_uuid = s3_uuid

        web_doc.save()

    # print(f"Step 10: adding missing embedding for model >{embedding_model}")
    # embedding_needed = websites.get_embedding_missing(embedding_model)
    # website_nb = 1
    # embedding_needed_len = len(embedding_needed)
    # print(f"entries to analyze: {embedding_needed_len}")
    # for website_id in embedding_needed:
    #     web_doc = StalkerWebDocumentDB(document_id=website_id)
    #
    #     progress = round((website_nb / embedding_needed_len) * 100)
    #     print(f"Working on ID:{web_doc.id} ({website_nb} from {embedding_needed_len} {progress}%)"
    #           f" {web_doc.document_type}" f"url: {web_doc.url}")
    #     website_nb += 1
    #     web_doc.embedding_add(model=embedding_model)
    #     web_doc.save()

    websites.close()
