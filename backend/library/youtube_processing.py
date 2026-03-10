import json
import logging
import os
import mimetypes
import time
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

import assemblyai as aai
import boto3
import requests
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled

from library.api.aws.s3_aws import s3_file_exist
from library.api.aws.transcript import aws_transcript
from sqlalchemy.orm import Session

from library.db.models import WebDocument
from library.models.stalker_document_status import StalkerDocumentStatus
from library.models.stalker_document_status_error import StalkerDocumentStatusError
from library.models.stalker_document_type import StalkerDocumentType
from library.stalker_youtube_file import StalkerYoutubeFile
from library.text_detect_language import compare_language, text_language_detect
from library.text_transcript import youtube_titles_split_with_chapters, youtube_titles_to_text
from library.transcript import transcript_price

logger = logging.getLogger(__name__)


def clean_youtube_url(url: str) -> str:
    """Remove extra query parameters from YouTube URL, keeping only 'v'."""
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    if 'v' in params:
        clean_query = urlencode({'v': params['v'][0]})
        return urlunparse(parsed._replace(query=clean_query))
    return url


def process_youtube_url(
    session: Session,
    youtube_url: str,
    language: str | None = None,
    chapter_list: str | None = None,
    note: str | None = None,
    source: str = "own",
    force_reprocess: bool = False,
    cache_dir: str | None = None,
    transcript_provider: str | None = None,
    ai_summary_needed: bool = False,
    llm_model: str | None = None,
    skip_captions: bool = False,
) -> "WebDocument":
    """Process a YouTube URL: fetch metadata, download captions/transcription, store in DB.

    If the URL already exists in the database, the existing document is updated.
    If not, a new document is created.

    The caller owns the session lifecycle — this function commits per-document
    but never closes the session.

    Returns the WebDocument ORM instance with all processed data.
    """

    t_start = time.time()

    # Clean URL — remove playlist, timestamp and other extra params
    youtube_url = clean_youtube_url(youtube_url)

    # Config from env vars with parameter fallbacks
    cache_dir = cache_dir or os.getenv("CACHE_DIR", "cache")
    transcript_provider = transcript_provider or os.getenv("TRANSCRIPT_PROVIDER", "assemblyai")
    s3_bucket_transcript = os.getenv("AWS_S3_TRANSCRIPT")

    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir)

    # Load or create document in DB
    web_document = WebDocument.get_by_url(session, youtube_url)

    if web_document is None:
        # New document — create via ORM
        logger.info(f"New YouTube URL, creating document: {youtube_url}")
        web_document = WebDocument(url=youtube_url)
        web_document.set_document_type("youtube")
        web_document.source = source
        if language:
            web_document.language = language
        if chapter_list:
            web_document.chapter_list = chapter_list
        if note:
            web_document.note = note
        session.add(web_document)
        session.commit()
    else:
        logger.info(f"Document already exists in DB with ID: {web_document.id}")

    if not force_reprocess and web_document.id and web_document.document_state == StalkerDocumentStatus.EMBEDDING_EXIST:
        logger.info(f"Document {web_document.id} already has embeddings, skipping.")
        return web_document

    # Create YouTube file object
    t0 = time.time()
    youtube_file = StalkerYoutubeFile(
        youtube_url=web_document.url, media_type="video", cache_directory=cache_dir
    )
    logger.info(f"StalkerYoutubeFile init: {time.time() - t0:.2f}s")
    youtube_file.chapters_string = web_document.chapter_list

    if not youtube_file.valid:
        logger.error(youtube_file.error)
        return web_document

    # Fetch metadata if URL_ADDED and pytube available
    if web_document.document_state == StalkerDocumentStatus.URL_ADDED and youtube_file.can_pytube:
        logger.info("Updating document metadata from YouTube")
        web_document.title = youtube_file.title
        web_document.url = youtube_file.url
        web_document.original_id = youtube_file.video_id
        web_document.text = youtube_file.text
        web_document.text_raw = youtube_file.text
        web_document.document_type = StalkerDocumentType.youtube
        web_document.document_length = youtube_file.length_seconds
        session.commit()

    logger.info(f"Video ID: {youtube_file.video_id}")

    # Set status to NEED_TRANSCRIPTION
    logger.info("Setting status NEED_TRANSCRIPTION")
    web_document.document_state = StalkerDocumentStatus.NEED_TRANSCRIPTION
    session.commit()

    # Default language
    if not web_document.language:
        default_lang = os.getenv("YOUTUBE_DEFAULT_LANGUAGE")
        logger.info(f"Setting language to '{default_lang}' as default for YouTube documents")
        web_document.language = default_lang

    # Try YouTube captions first
    if web_document.document_state == StalkerDocumentStatus.NEED_TRANSCRIPTION and skip_captions:
        logger.info("Skipping YouTube captions (skip_captions=True, likely IP blocked)")
        web_document.document_state = StalkerDocumentStatus.TEMPORARY_ERROR
        web_document.document_state_error = StalkerDocumentStatusError.CAPTIONS_FETCH_ERROR
        session.commit()
        return web_document

    if web_document.document_state == StalkerDocumentStatus.NEED_TRANSCRIPTION:
        t0 = time.time()
        logger.info("Trying to use captions from YouTube")
        try:
            yt_language = web_document.language
            if yt_language == 'pl-PL':
                yt_language = 'pl'

            ytt_api = YouTubeTranscriptApi()
            transcript_list = ytt_api.list(youtube_file.video_id)
            available_languages = [trans.language_code for trans in transcript_list]

            if yt_language not in available_languages:
                logger.warning(f"Language '{yt_language}' not found. Trying default language 'en' (English).")
                yt_language = 'en'

            srt = ytt_api.fetch(youtube_file.video_id, languages=[yt_language])
            transcript_text = json.dumps(srt.to_raw_data())
            logger.info(f"Successfully retrieved transcript in language: {yt_language}")

            if transcript_text:
                logger.info("Checking if transcript language matches expected language")
                string_to_check = youtube_titles_to_text(transcript_text)
                language_detected = text_language_detect(string_to_check[0:600])
                logger.info(f"Detected language: {language_detected}")

                if not compare_language(language_detected, web_document.language):
                    logger.info(
                        f"Language detected >{language_detected}< differs from expected >{web_document.language}<, "
                        f"captions language mismatch"
                    )
                    web_document.text = youtube_titles_to_text(transcript_text)
                    web_document.text_raw = web_document.text
                    web_document.language = language_detected
                    web_document.document_state = StalkerDocumentStatus.ERROR
                    web_document.document_state_error = StalkerDocumentStatusError.CAPTIONS_LANGUAGE_MISMATCH
                    session.commit()
                    return web_document
                else:
                    if transcript_text and web_document.chapter_list:
                        string_all = youtube_titles_split_with_chapters(
                            transcript_text, web_document.chapter_list
                        )
                        web_document.text = string_all
                        web_document.document_state = StalkerDocumentStatus.NEED_MANUAL_REVIEW
                        session.commit()
                    elif transcript_text:
                        web_document.text = youtube_titles_to_text(transcript_text)
                        web_document.document_state = StalkerDocumentStatus.NEED_MANUAL_REVIEW
                        session.commit()

                web_document.text_raw = web_document.text
                session.commit()

        except TranscriptsDisabled:
            logger.info(f"The video at {web_document.url} has its transcripts disabled.")
            web_document.youtube_captions = False
            session.commit()

        except Exception as e:
            logger.error(f"An unexpected error occurred while fetching captions: {e}")
            session.rollback()
            web_document.document_state = StalkerDocumentStatus.TEMPORARY_ERROR
            web_document.document_state_error = StalkerDocumentStatusError.CAPTIONS_FETCH_ERROR
            session.commit()
            return web_document

        logger.info(f"YouTube captions step: {time.time() - t0:.2f}s")

    # If still NEED_TRANSCRIPTION — check if paid transcription is authorized
    t0 = time.time()
    if web_document.document_state == StalkerDocumentStatus.NEED_TRANSCRIPTION:
        if not web_document.transcript_needed:
            logger.info("YouTube captions not available and transcript_needed=False — skipping paid transcription")
            web_document.document_state = StalkerDocumentStatus.ERROR
            web_document.document_state_error = StalkerDocumentStatusError.NO_CAPTIONS_AVAILABLE
            session.commit()
            return web_document

        logger.info(f"Status: {web_document.document_state}")
        logger.info(f"Title: {web_document.title}")
        logger.info(f"Description: {youtube_file.description}")
        logger.info(f"Length: {youtube_file.length_minutes} min ({youtube_file.length_seconds} seconds)")

        logger.info("Transcription cost estimates:")
        for provider, price in transcript_price(youtube_file.length_seconds).items():
            logger.info(f"{provider}: {price}$")

        if web_document.transcript_job_id:
            logger.info(f"Transcription job >{web_document.transcript_job_id}< exists, skipping download...")
        else:
            logger.info(f"Checking if local copy exists ({youtube_file.path})...")
            if os.path.exists(youtube_file.path):
                logger.info("Local copy exists, not downloading")
            else:
                logger.info("No local copy, starting download...")
                youtube_file.download_video()
                logger.info("[DONE]")

        if transcript_provider == "assemblyai":
            logger.info("Using >assemblyai< as transcript source")
            aai.settings.api_key = os.getenv("ASSEMBLYAI")

            config = aai.TranscriptionConfig(language_code=web_document.language)

            if not web_document.transcript_job_id:
                transcriber = aai.Transcriber(config=config)
                logger.info("Making transcription...")
                transcript = transcriber.transcribe(youtube_file.path)
                web_document.transcript_job_id = transcript.id
                logger.info(f"[DONE] Transcript job ID: >{transcript.id}<")
                web_document.document_state = StalkerDocumentStatus.TRANSCRIPTION_IN_PROGRESS
                session.commit()

            transcript = aai.Transcript.get_by_id(web_document.transcript_job_id)
            if transcript.status == aai.TranscriptStatus.error:
                logger.error(f"Transcription failed: {transcript.error}")
            elif transcript.status == "completed":
                text_raw = ""
                for paragraph in transcript.get_paragraphs():
                    if paragraph.text and len(paragraph.text) > 0:
                        text_raw += paragraph.text + "\n\n"

                logger.debug(text_raw)
                web_document.text_raw = transcript.text
                web_document.text = text_raw
                web_document.document_state = StalkerDocumentStatus.TRANSCRIPTION_DONE
                session.commit()
            else:
                logger.info(f"Transcription status: {transcript.status}")

        elif transcript_provider == "aws":
            media_format = mimetypes.guess_type(youtube_file.path)[0]

            boto_session = boto3.Session(
                aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
                region_name=os.getenv("AWS_REGION"),
            )

            logger.info("Checking if file to transcription is on S3...")
            if not s3_file_exist(s3_bucket_transcript, youtube_file.filename):
                s3_client = boto_session.client(service_name='s3', region_name='us-east-1')
                logger.info("Uploading file to S3...")
                with open(youtube_file.path, 'rb') as file:
                    s3_client.upload_fileobj(file, s3_bucket_transcript, youtube_file.filename)
                logger.info("[DONE]")

            logger.info("Making transcription...")
            response = aws_transcript(
                s3_bucket=s3_bucket_transcript, s3_key=youtube_file.filename, media_format=media_format
            )

            if response['status'] == "COMPLETED" or response['status'] == "success":
                remote_file = response['remote_file']
                logger.info("Downloading transcript to local file")
                response = requests.get(remote_file)

                with open(youtube_file.transcript_file, 'wb') as file:
                    file.write(response.content)

                web_document.text_raw = response.content
                session.commit()
                logger.info("[DONE]")
            else:
                logger.info(f"Transcription status: {response['status']}")
        else:
            logger.error(f"Unknown transcript provider: {transcript_provider}")

        logger.info(f"External transcription step: {time.time() - t0:.2f}s")

    logger.info(f"Total process_youtube_url: {time.time() - t_start:.2f}s")
    return web_document
