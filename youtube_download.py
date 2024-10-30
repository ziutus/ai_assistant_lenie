import json
import logging
import mimetypes
import os

import assemblyai as aai
import boto3
import requests
from dotenv import load_dotenv
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled

from library.ai import ai_ask
from library.api.aws.s3_aws import s3_file_exist
from library.api.aws.transcript import aws_transcript
from library.stalker_web_document import StalkerDocumentStatus, StalkerDocumentType
from library.stalker_web_document_db import StalkerWebDocumentDB
from library.stalker_web_documents_db_postgresql import WebsitesDBPostgreSQL
from library.stalker_youtube_file import StalkerYoutubeFile
from library.text_detect_language import text_language_detect
from library.text_transcript import youtube_titles_split_with_chapters, youtube_titles_to_text
from library.transcript import transcript_price

logging.basicConfig(level=logging.INFO)  # Change level as per your need
load_dotenv()


def compare_language(language_1: str, language_2: str):
    if language_1 == language_2:
        return True
    if language_1 == 'pl-PL' and language_2 == 'pl':
        return True
    if language_1 == 'pl' and language_2 == 'pl-PL':
        return True
    return False

if __name__ == '__main__':
    cache_dir = os.getenv("CACHE_DIR")
    s3_bucket = os.getenv("AWS_S3_TRANSCRIPT")
    transcript_provider = os.getenv("TRANSCRIPT_PROVIDER")
    llm_model = os.getenv("AI_MODEL_SUMMARY")
    interactive: bool = False

    aws_xray_enabled = os.getenv("AWS_XRAY_ENABLED")
    print(f"aws_xray_enabled: {aws_xray_enabled}")

    if aws_xray_enabled:
        from aws_xray_sdk.core import xray_recorder, patch_all

        # Konfiguracja X-Ray
        xray_recorder.configure(service='lenie_ai')
        patch_all()  # Automatyczne łatanie wszystkich bibliotek

    if aws_xray_enabled:
        xray_recorder.begin_segment('MainSegment')  # Rozpoczęcie głównego segmentu

    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir)

    websites = WebsitesDBPostgreSQL()
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

        if web_document.document_state == StalkerDocumentStatus.URL_ADDED:
            logging.info("updating data in database about documents")
            web_document.document_state = StalkerDocumentStatus.NEED_TRANSCRIPTION
            web_document.title = youtube_file.title
            web_document.url = youtube_file.url
            web_document.original_id = youtube_file.video_id
            web_document.text = youtube_file.text
            web_document.document_type = StalkerDocumentType.youtube
            web_document.document_length = youtube_file.length_seconds
            web_document.save()

        logging.info(f"video ID: {youtube_file.video_id}")
        # description = youtube_file.description
        # logging.info(f"DEBUG description: {description}")

        if not web_document.language:
            logging.info(f"setup language to '{os.getenv('YOUTUBE_DEFAULT_LANGUAGE')}' as default for youtube documents")
            web_document.language = os.getenv("YOUTUBE_DEFAULT_LANGUAGE")

        if web_document.document_state == StalkerDocumentStatus.NEED_TRANSCRIPTION:
            logging.info("Trying to use captions from youtube")
            try:
                language= web_document.language
                if language == 'pl-PL':
                    language = 'pl'

                transcript_list = YouTubeTranscriptApi.list_transcripts(youtube_file.video_id)
                srt = YouTubeTranscriptApi.get_transcript(video_id=youtube_file.video_id,
                                                          languages=[language],)
                transcript_text = json.dumps(srt)
                logging.info("Took transcription from YouTube")

                if transcript_text:
                    logging.info("checking if it is really correctly language")
                    sting_to_check = youtube_titles_to_text(transcript_text)
                    language_detected = text_language_detect(sting_to_check[0:600])
                    logging.info(f"detected language: {language_detected}")

                    # if language_detected != web_document.language:
                    if not compare_language(language_detected, web_document.language):
                        logging.info(f"Language detected >{language_detected}< is different then setup >{web_document.language}<, need to make transcription")
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

            except TranscriptsDisabled:
                logging.info(f"The video at {web_document.url} has its transcripts disabled.")
                web_document.youtube_captions = False
                web_document.save()

        if web_document.document_state == StalkerDocumentStatus.NEED_TRANSCRIPTION:

            logging.info(f"Status: {web_document.document_state}")
            logging.info(f"Title: {youtube_file.title}")
            logging.info(f"Description: {youtube_file.description}")
            logging.info(f"Length: {youtube_file.length_minutes} min ({youtube_file.length_seconds} seconds)")
            logging.info(f"document status: {web_document.document_state}")

            logging.info("Transcription will cost on:")
            for provider, price in transcript_price(youtube_file.length_seconds).items():
                logging.info(f"{provider}: {price}$")

            if web_document.transcript_job_id:
                logging.info(f"DEBUG: transcription job >{web_document.transcript_job_id}< exist, downloading file not needed...")
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
                if not s3_file_exist(s3_bucket, youtube_file.filename):
                    s3_client = session.client(service_name='s3', region_name='us-east-1')

                    logging.info("Upload file to S3...")
                    with open(youtube_file.path, 'rb') as file:
                        s3_client.upload_fileobj(file, s3_bucket, youtube_file.filename)
                    logging.info("[DONE]")

                logging.info("Making transcription...")
                response = aws_transcript(s3_bucket=s3_bucket, s3_key=youtube_file.filename, media_format=media_format)

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

        if aws_xray_enabled:
            xray_recorder.end_segment()  # Koniec głównego segmentu
