import json
import logging
import os
import uuid

from markitdown import MarkItDown
import boto3
from dotenv import load_dotenv
import mimetypes
import assemblyai as aai
import requests

# Importacja własnych modułów
from library.website.website_download_context import download_raw_html, webpage_raw_parse, webpage_text_clean

from library.ai import ai_ask
from library.api.aws.s3_aws import s3_file_exist
from library.api.aws.transcript import aws_transcript
from library.stalker_web_document import StalkerDocumentStatus, StalkerDocumentType, StalkerDocumentStatusError
from library.stalker_web_document_db import StalkerWebDocumentDB
from library.stalker_web_documents_db_postgresql import WebsitesDBPostgreSQL
from library.stalker_youtube_file import StalkerYoutubeFile
from library.text_detect_language import text_language_detect
from library.text_transcript import youtube_titles_split_with_chapters, youtube_titles_to_text
from library.transcript import transcript_price
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled
from library.embedding import embedding_need_translation

# Ładowanie zmiennych środowiskowych
load_dotenv()

logging.basicConfig(level=logging.INFO)  # Change level as per your need

aws_xray_enabled = os.getenv("AWS_XRAY_ENABLED")
print(f"aws_xray_enabled: {aws_xray_enabled}")

if aws_xray_enabled:
    from aws_xray_sdk.core import xray_recorder, patch_all
    from aws_xray_sdk.core import patch

    # Konfiguracja X-Ray
    xray_recorder.configure(service='lenie_ai')
    patch_all()  # Automatyczne łatanie wszystkich bibliotek


def compare_language(language_1: str, language_2: str):
    if language_1 == language_2:
        return True
    if language_1 == 'pl-PL' and language_2 == 'pl':
        return True
    if language_1 == 'pl' and language_2 == 'pl-PL':
        return True
    return False


"""
TODO: add limits for asemblay.ai upload files (check), see: https://www.assemblyai.com/docs/concepts/faq
Currently, the maximum file size that can be submitted to the /v2/transcript endpoint for transcription is 5GB,
and the maximum duration is 10 hours.
The maximum file size for a local file uploaded to the API via the /v2/upload endpoint is 2.2GB.
"""

if __name__ == '__main__':
    if aws_xray_enabled:
        xray_recorder.begin_segment('MainSegment')  # Rozpoczęcie głównego segmentu

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
            finally:
                if aws_xray_enabled:
                    xray_recorder.end_subsegment()  # Koniec podsegmentu

    websites = WebsitesDBPostgreSQL()

    print("Step 2 a: putting youtube movies data into database")
    website_data = websites.get_youtube_just_added()
    logging.info(f"Entries to analyze: {len(website_data)}")
    for movie in website_data:
        logging.info(f"Working on document ID: {movie[0]}")
        web_document = StalkerWebDocumentDB(document_id=int(movie[0]))
        youtube_file = StalkerYoutubeFile(youtube_url=web_document.url, media_type="video", cache_directory=cache_dir)
        youtube_file.chapters_string = web_document.chapter_list

        if web_document.id and web_document.status_code == StalkerDocumentStatus.EMBEDDING_EXIST:
            logging.info(f"This file exist in our database with embedding with ID: {web_document.id}")
            logging.info("Going to next file...")
            continue

        if not youtube_file.valid:
            logging.error(youtube_file.error)
            continue

        if web_document.document_state == StalkerDocumentStatus.URL_ADDED and youtube_file.can_pytube:
            logging.info("updating data in database about documents")
            web_document.title = youtube_file.title
            web_document.url = youtube_file.url
            web_document.original_id = youtube_file.video_id
            web_document.text = youtube_file.text
            web_document.text_raw = youtube_file.text
            web_document.document_type = StalkerDocumentType.youtube
            web_document.document_length = youtube_file.length_seconds
            web_document.save()

        logging.info(f"video ID: {youtube_file.video_id}")
        # description = youtube_file.description
        # logging.info(f"DEBUG description: {description}")

        logging.info("Setup status NEED_TRANSCRIPTION")
        web_document.document_state = StalkerDocumentStatus.NEED_TRANSCRIPTION
        web_document.save()

        if not web_document.language:
            logging.info(
                f"setup language to '{os.getenv('YOUTUBE_DEFAULT_LANGUAGE')}' as default for youtube documents")
            web_document.language = os.getenv("YOUTUBE_DEFAULT_LANGUAGE")

        if web_document.document_state == StalkerDocumentStatus.NEED_TRANSCRIPTION:
            logging.info("Trying to use captions from youtube")
            try:
                language = web_document.language
                if language == 'pl-PL':
                    language = 'pl'

                transcript_list = YouTubeTranscriptApi.list_transcripts(youtube_file.video_id)
                available_languages = [trans.language_code for trans in transcript_list]

                if language not in available_languages:
                    logging.warning(
                        f"Language '{language}' not found. Trying default language 'en' (English)."
                    )
                    language = 'en'  # Try using English as a fallback option if using 'pl' fails

                srt = YouTubeTranscriptApi.get_transcript(video_id=youtube_file.video_id,
                                                          languages=[language], )
                transcript_text = json.dumps(srt)
                logging.info(f"Successfully retrieved transcript in language: {language}")

                if transcript_text:
                    logging.info("checking if it is really correctly language")
                    sting_to_check = youtube_titles_to_text(transcript_text)
                    language_detected = text_language_detect(sting_to_check[0:600])
                    logging.info(f"detected language: {language_detected}")

                    # if language_detected != web_document.language:
                    if not compare_language(language_detected, web_document.language):
                        logging.info(
                            f"Language detected >{language_detected}< is different then setup >{web_document.language}<, need to make transcription")
                        web_document.document_state = StalkerDocumentStatus.NEED_TRANSCRIPTION
                        web_document.language = language_detected
                        web_document.save()
                    else:
                        if transcript_text and web_document.chapter_list:
                            string_all = youtube_titles_split_with_chapters(transcript_text, web_document.chapter_list)
                            web_document.text = string_all
                            web_document.document_state = StalkerDocumentStatus.NEED_MANUAL_REVIEW
                            web_document.save()
                        elif transcript_text:
                            web_document.text = youtube_titles_to_text(transcript_text)
                            web_document.document_state = StalkerDocumentStatus.NEED_MANUAL_REVIEW
                            web_document.save()

                    web_document.text_raw = web_document.text
                    web_document.save()

            except TranscriptsDisabled:
                logging.info(f"The video at {web_document.url} has its transcripts disabled.")
                web_document.youtube_captions = False
                web_document.save()

            except Exception as e:
                logging.error(f"An unexpected error occurred: {e}")

        if web_document.document_state == StalkerDocumentStatus.NEED_TRANSCRIPTION:

            logging.info(f"Status: {web_document.document_state}")
            logging.info(f"Title: {web_document.title}")
            logging.info(f"Description: {youtube_file.description}")
            logging.info(f"Length: {youtube_file.length_minutes} min ({youtube_file.length_seconds} seconds)")
            logging.info(f"document status: {web_document.document_state}")

            logging.info("Transcription will cost on:")
            for provider, price in transcript_price(youtube_file.length_seconds).items():
                logging.info(f"{provider}: {price}$")

            if web_document.transcript_job_id:
                logging.info(
                    f"DEBUG: transcription job >{web_document.transcript_job_id}< exist, downloading file not needed...")
            else:
                logging.info(f"Checking if local copy exists ({youtube_file.path})...")
                if os.path.exists(youtube_file.path):
                    logging.info("Exist, not loading files")
                else:
                    logging.info("Not exist local copy")
                    logging.info("Starting file download...")
                    youtube_file.download_video()
                    logging.info("[DONE]")

            if transcript_provider == "assemblyai":
                logging.info("Using >assemblyai< as transcript source")
                aai.settings.api_key = os.getenv("ASSEMBLYAI")

                config = aai.TranscriptionConfig(language_code=web_document.language)

                if not web_document.transcript_job_id:
                    transcriber = aai.Transcriber(config=config)

                    logging.info("Making transcription...")
                    transcript = transcriber.transcribe(youtube_file.path)
                    web_document.transcript_job_id = transcript.id
                    logging.info("[DONE]")
                    logging.info(f"The transcript job ID:>{transcript.id}<")
                    web_document.document_state = StalkerDocumentStatus.TRANSCRIPTION_IN_PROGRESS
                    web_document.save()

                transcript = aai.Transcript.get_by_id(web_document.transcript_job_id)
                if transcript.status == aai.TranscriptStatus.error:
                    logging.info(f"Transcription failed: {transcript.error}")
                elif transcript.status == "completed":

                    text_raw = ""
                    for paragraph in transcript.get_paragraphs():
                        if paragraph.text and len(paragraph.text) > 0:
                            text_raw += paragraph.text + "\n\n"

                    logging.debug(text_raw)
                    web_document.text_raw = transcript.text
                    web_document.text = text_raw
                    web_document.document_state = StalkerDocumentStatus.TRANSCRIPTION_DONE
                    web_document.save()

                else:
                    logging.info(f"{transcript.status}")

            elif transcript_provider == "aws":

                uri_path = f"local://{youtube_file.path}"
                media_format = mimetypes.guess_type(youtube_file.path)[0]

                session = boto3.Session(
                    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
                    region_name=os.getenv("AWS_REGION")
                )

                logging.info("Checking if file to transcription is on S3...")
                if not s3_file_exist(s3_bucket_transcript, youtube_file.filename):
                    s3_client = session.client(service_name='s3', region_name='us-east-1')

                    logging.info("Upload file to S3...")
                    with open(youtube_file.path, 'rb') as file:
                        s3_client.upload_fileobj(file, s3_bucket_transcript, youtube_file.filename)
                    logging.info("[DONE]")

                logging.info("Making transcription...")
                response = aws_transcript(s3_bucket=s3_bucket_transcript, s3_key=youtube_file.filename,
                                          media_format=media_format)

                if response['status'] == "COMPLETED" or response['status'] == "success":
                    remote_file = response['remote_file']
                    logging.info("Downloading transcript to local file")
                    response = requests.get(remote_file)

                    with open(youtube_file.transcript_file, 'wb') as file:
                        file.write(response.content)

                    web_document.text_raw = response.content
                    web_document.save()
                    logging.info("[DONE]")
                else:
                    logging.info(f"Transcription status: {response['status']}")
                    continue

            else:
                logging.error(f"Unknown translate provider {transcript_provider}")

        # if web_document.document_state == StalkerDocumentStatus.TRANSCRIPTION_DONE:
        #     logging.info("Splitting text by chapters")
        #     youtube_file.text = web_document.text
        #     youtube_file.transcription_split_by_chapters()
        #
        #     web_document.text = youtube_file.text
        #     web_document.document_state = StalkerDocumentStatus.NEED_MANUAL_REVIEW
        #     web_document.save()

        # logging.info(f"Text length: {len(web_document.text.split(' '))}")

        if web_document.ai_summary_needed and not web_document.summary and web_document.text:
            prompt = f"Wykonaj podsumowanie w punktach:\n\n TEXT: {web_document.text} "
            response = ai_ask(query=prompt, model=llm_model).response_text
            logging.info(response)
            web_document.summary = response
            web_document.save()

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
            if aws_xray_enabled:
                xray_recorder.end_subsegment()  # Koniec podsegmentu

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

    if aws_xray_enabled:
        xray_recorder.end_segment()  # Koniec głównego segmentu
