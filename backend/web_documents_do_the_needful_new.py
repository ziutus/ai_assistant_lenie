import argparse
import json
import logging
import os
import time
import uuid

script_start = time.monotonic()
print("=== web_documents_do_the_needful_new.py ===")

from library.config_loader import load_config  # noqa: E402

# Ładowanie konfiguracji (obsługuje .env, Vault, AWS SSM)
print("Loading configuration...", end=" ", flush=True)
t0 = time.monotonic()
cfg = load_config()
print(f"done ({time.monotonic() - t0:.1f}s)")

logging.basicConfig(level=logging.INFO)  # Change level as per your need

print(f"aws_xray_enabled: {cfg.get('AWS_XRAY_ENABLED')}")

missing_markdown_correct = False

"""
TODO: add limits for asemblay.ai upload files (check), see: https://www.assemblyai.com/docs/concepts/faq
Currently, the maximum file size that can be submitted to the /v2/transcript endpoint for transcription is 5GB,
and the maximum duration is 10 hours.
The maximum file size for a local file uploaded to the API via the /v2/upload endpoint is 2.2GB.
"""

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description="Document processing pipeline")
    parser.add_argument("--only-links", action="store_true", help="Process only 'link' documents")
    parser.add_argument("--only-webpage", action="store_true", help="Process only 'webpage' documents")
    parser.add_argument("--only-youtube", action="store_true", help="Process only 'youtube' documents")
    parser.add_argument("--only-movie", action="store_true", help="Process only 'movie' documents")
    parser.add_argument(
        "--clean-sqs",
        action="store_true",
        help="Only drain SQS queue (Step 1) and exit",
    )
    args = parser.parse_args()

    only_flags = [args.only_links, args.only_webpage, args.only_youtube, args.only_movie]
    has_only_filter = any(only_flags)

    process_types = {
        "link": args.only_links if has_only_filter else True,
        "webpage": args.only_webpage if has_only_filter else True,
        "youtube": args.only_youtube if has_only_filter else True,
        "movie": args.only_movie if has_only_filter else True,
    }

    print(f"Document types to process: {[t for t, enabled in process_types.items() if enabled]}")

    print(f"Using >{cfg.get('EMBEDDING_MODEL')}< for embedding")

    print(f"Initialization done in {time.monotonic() - script_start:.1f}s")
    print()

    print("Setting up Webshare proxy...", end=" ", flush=True)
    t0 = time.monotonic()
    webshare_api_key = cfg.get("WEBSHARE_API_KEY")
    webshare_proxy_available = False
    if webshare_api_key:
        try:
            from library.webshare_ip_auth import ensure_ip_authorized, check_bandwidth
            ensure_ip_authorized(webshare_api_key)
            bw = check_bandwidth(webshare_api_key)
            print(f"Webshare proxy: {bw['used_mb']} MB used / {bw['limit_mb']:.0f} MB limit — {bw['remaining_mb']} MB remaining")
            webshare_proxy_available = bw["available"]
            if not webshare_proxy_available:
                print("WARNING: Webshare bandwidth exhausted — YouTube captions will use direct connection")
        except Exception as e:
            print(f"WARNING: Webshare setup failed: {e}")
    else:
        print("skipped (no API key)", end="")
    print(f" ({time.monotonic() - t0:.1f}s)")

    if not cfg.get("AWS_S3_WEBSITE_CONTENT"):
        print("The S3 bucket for text and html files is not set, exiting.")
        exit(1)

    cache_dir = os.path.join(cfg.get('CACHE_DIR') or "tmp", "markdown")
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir)

    print("AWS REGION: ", cfg.get("AWS_REGION"))

    # Create boto3 session at top level — needed by Step 1 (SQS) and Step 2b (S3)
    print("Creating AWS boto3 session...", end=" ", flush=True)
    t0 = time.monotonic()
    import boto3
    boto_session = boto3.session.Session(
        aws_access_key_id=cfg.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=cfg.get("AWS_SECRET_ACCESS_KEY"),
        region_name=cfg.get("AWS_REGION")
    )
    print(f"done ({time.monotonic() - t0:.1f}s)")

    aws_session = boto3.Session(region_name=cfg.get("AWS_REGION"))
    try:
        sts = aws_session.client("sts")
        identity = sts.get_caller_identity()
        actual_account = identity['Account']
        print(f"AWS account: {actual_account}, identity: {identity['Arn']}")
        expected_account = cfg.get("AWS_ACCOUNT_ID")
        if expected_account and actual_account != expected_account:
            print(f"ERROR: AWS account mismatch! Expected: {expected_account}, got: {actual_account}")
            exit(1)
    except Exception as e:
        print(f"WARNING: Could not determine AWS identity: {e}")

    s3_check = aws_session.client("s3")
    try:
        s3_check.head_bucket(Bucket=cfg.get("AWS_S3_WEBSITE_CONTENT"))
    except Exception as e:
        print(f"S3 bucket '{cfg.get('AWS_S3_WEBSITE_CONTENT')}' is not accessible: {e}")
        exit(1)

    # ORM & domain imports (deferred to reduce startup time)
    print("Loading ORM & domain modules...", end=" ", flush=True)
    t0 = time.monotonic()
    from library.db.models import WebDocument
    from library.db.engine import get_session
    from library.document_service import DocumentService
    from library.models.stalker_document_status import StalkerDocumentStatus
    from library.models.stalker_document_type import StalkerDocumentType
    from library.models.stalker_document_status_error import StalkerDocumentStatusError
    from library.search_service import SearchService
    from library.stalker_web_documents_db_postgresql import WebsitesDBPostgreSQL
    print(f"done ({time.monotonic() - t0:.1f}s)")

    # ORM session — single session for entire script
    print("Connecting to database...", end=" ", flush=True)
    t0 = time.monotonic()
    session = get_session()
    print(f"done ({time.monotonic() - t0:.1f}s)")

    print(f"\nTotal startup time: {time.monotonic() - script_start:.1f}s")
    print("=" * 50)
    try:
        print("\nStep 1: Taking pages to put into RDS database")
        step_start = time.monotonic()
        if not args.clean_sqs:
            print("ignoring cleaning the SQS queue")
        else:
            sqs = boto_session.client('sqs')
            doc_service = DocumentService(session)

            while True:
                response = sqs.receive_message(
                    QueueUrl=cfg.get('AWS_QUEUE_URL_ADD'),
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

                        # Map camelCase SQS fields to snake_case metadata
                        metadata = {}
                        metadata["source"] = link_data.get("source", "own")
                        if 'chapterList' in link_data:
                            metadata["chapter_list"] = link_data["chapterList"]
                        if 'chapter_list' in link_data:
                            metadata["chapter_list"] = link_data["chapter_list"]
                        if 'language' in link_data:
                            metadata["language"] = link_data["language"]
                        if 'makeAISummary' in link_data:
                            metadata["ai_summary_needed"] = link_data["makeAISummary"]
                        if 'note' in link_data:
                            metadata["note"] = link_data["note"]
                        if 's3_uuid' in link_data:
                            metadata["s3_uuid"] = link_data["s3_uuid"]
                        if 'title' in link_data:
                            metadata["title"] = link_data["title"]
                        if 'paywall' in link_data:
                            metadata["paywall"] = link_data["paywall"]

                        doc, status = doc_service.import_document(
                            url=link_data["url"],
                            document_type=link_data["type"],
                            skip_if_exists=True,
                            **metadata,
                        )

                        if status == "skipped":
                            print("This Url exist in, ignoring ")
                            sqs.delete_message(
                                QueueUrl=cfg.get('AWS_QUEUE_URL_ADD'),
                                ReceiptHandle=message['ReceiptHandle']
                            )
                            continue

                        print(f"Added to database with ID {doc.id}")
                        print("[DONE]")

                        sqs.delete_message(
                            QueueUrl=cfg.get('AWS_QUEUE_URL_ADD'),
                            ReceiptHandle=message['ReceiptHandle']
                        )
                    except Exception as e:
                        session.rollback()
                        print(f'An error occurred: {e}')

        print(f"Step 1 completed in {time.monotonic() - step_start:.1f}s")

        websites = WebsitesDBPostgreSQL(session=session)

        print("\nStep 2a: putting youtube movies data into database")
        step_start = time.monotonic()
        if not process_types["youtube"]:
            print("ignoring youtube movies")
        else:
            from library.youtube_processing import process_youtube_url
            youtube_captions_blocked = False
            website_data = websites.get_youtube_just_added()
            logging.info(f"Entries to analyze: {len(website_data)}")
            for movie in website_data:
                logging.info(f"Working on document ID: {movie[0]}")
                try:
                    web_document = WebDocument.get_by_id(session, int(movie[0]))
                    if web_document is None:
                        logging.error(f"Document {movie[0]} not found")
                        continue
                    result = process_youtube_url(
                        session=session,
                        youtube_url=web_document.url,
                        language=web_document.language,
                        chapter_list=web_document.chapter_list,
                        ai_summary_needed=web_document.ai_summary_needed,
                        cache_dir=os.path.join(cfg.get('CACHE_DIR') or "tmp", "youtube_to_text"),
                        llm_model=cfg.get("AI_MODEL_SUMMARY"),
                        skip_captions=youtube_captions_blocked,
                        webshare_api_key=cfg.get("WEBSHARE_API_KEY"),
                    )
                    if result.document_state_error == StalkerDocumentStatusError.CAPTIONS_FETCH_ERROR.name \
                            and not youtube_captions_blocked:
                        youtube_captions_blocked = True
                        logging.warning("YouTube captions blocked — skipping captions for remaining videos")
                except Exception as e:
                    session.rollback()
                    logging.error(f"Error processing document {movie[0]}: {e}")

        print(f"Step 2a completed in {time.monotonic() - step_start:.1f}s")

        print("\nStep 2b: Downloading websites (or taking from S3) and putting data into database")
        step_start = time.monotonic()
        if not process_types["webpage"]:
            print("ignoring webpages")
        else:
            from library.website.website_download_context import download_raw_html, webpage_raw_parse, webpage_text_clean

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
                            print(f"* Reading text of article from S3 bucket >{cfg.get('AWS_S3_WEBSITE_CONTENT')}< and file: >{s3_uuid}.txt<", end=" ")
                            obj = s3.get_object(Bucket=cfg.get("AWS_S3_WEBSITE_CONTENT"), Key=f"{s3_uuid}.txt")
                            content = obj['Body'].read().decode('utf-8')
                            web_doc = WebDocument.get_by_url(session, url)
                            if web_doc is None:
                                web_doc = WebDocument(url=url)
                                session.add(web_doc)
                            web_doc.text = content
                            print('[DONE]')

                            print(f"* Reading text of article from S3 bucket >{cfg.get('AWS_S3_WEBSITE_CONTENT')}< and file: >{s3_uuid}.html<", end=" ")
                            obj = s3.get_object(Bucket=cfg.get('AWS_S3_WEBSITE_CONTENT'), Key=f"{s3_uuid}.html")
                            content = obj['Body'].read().decode('utf-8')

                            doc_cache_dir = os.path.join(cache_dir, str(s3_uuid))
                            os.makedirs(doc_cache_dir, exist_ok=True)
                            page_file = os.path.join(doc_cache_dir, f"{s3_uuid}.html")
                            with open(page_file, 'w', encoding="utf-8") as file:
                                file.write(content)

                            from markitdown import MarkItDown
                            md = MarkItDown()
                            result = md.convert(page_file)

                            md_file = os.path.join(doc_cache_dir, f"{s3_uuid}.md")
                            with open(md_file, 'w', encoding="utf-8") as file:
                                file.write(result.text_content)

                            md_clean_file = os.path.join(doc_cache_dir, f"{s3_uuid}_clean.md")
                            md_cleaned = result.text_content

                            md_cleaned = webpage_text_clean(url, md_cleaned)

                            web_doc.text_md = md_cleaned

                            with open(f"{md_clean_file}", 'w', encoding="utf-8") as file:
                                file.write(md_cleaned)

                            print('[DONE]')

                            web_doc.analyze()
                            web_doc.validate()

                            print(
                                "* ALL DONE, updating state to NEED_MANUAL_REVIEW (cleaning of text is needed) as it is >webpage<",
                                end=" ")
                            web_doc.document_state = StalkerDocumentStatus.NEED_MANUAL_REVIEW.name
                            print("[DONE]")
                            session.commit()

                        except Exception as e:
                            session.rollback()
                            print(f'An error occurred: {e}')
                            continue
                    else:
                        try:
                            print("* Downloading raw html from remote webpage", end=" ")
                            raw_html = download_raw_html(url)
                            if not raw_html:
                                print("empty response! [ERROR]")
                                web_doc = WebDocument.get_by_url(session, url)
                                if web_doc is None:
                                    web_doc = WebDocument(url=url)
                                    session.add(web_doc)
                                web_doc.document_state = StalkerDocumentStatus.ERROR.name
                                web_doc.document_state_error = StalkerDocumentStatusError.ERROR_DOWNLOAD.name
                                session.commit()
                                continue

                            print(round(len(raw_html) / 1024, 2), end="KB ")
                            print('[DONE]')

                            parse_result = webpage_raw_parse(url, raw_html)

                            web_doc = WebDocument.get_by_url(session, url)
                            if web_doc is None:
                                web_doc = WebDocument(url=url)
                                session.add(web_doc)

                            # Apply parse result fields
                            web_doc.text_raw = parse_result.text_raw
                            web_doc.text = parse_result.text
                            web_doc.language = parse_result.language
                            web_doc.title = parse_result.title
                            web_doc.summary = parse_result.summary

                            print(f"DEBUG: url:{web_doc.url}")

                            web_doc.analyze()
                            web_doc.validate()

                            if web_doc.document_state == StalkerDocumentStatus.URL_ADDED.name and web_doc.document_type == StalkerDocumentType.link.name:
                                web_doc.document_state = StalkerDocumentStatus.READY_FOR_EMBEDDING.name

                            session.commit()

                        except Exception as e:
                            session.rollback()
                            print(f"Error processing website {website_id}: {url}")
                            print(str(e))
                            continue

                        if web_doc.document_type == StalkerDocumentType.webpage.name:
                            print(
                                "* ALL DONE, updating state to NEED_MANUAL_REVIEW (cleaning of text is needed) as it is >webpage<",
                                end=" ")
                            web_doc.document_state = StalkerDocumentStatus.NEED_MANUAL_REVIEW.name
                            print("[DONE]")
                            session.commit()
                finally:
                    print(".")

                website_nb += 1

        print(f"Step 2b completed in {time.monotonic() - step_start:.1f}s")

        print("\nStep 3: Making correction of text and markdown entries")
        step_start = time.monotonic()
        from library.website.website_download_context import webpage_text_clean
        markdown_correction_needed = websites.get_list(document_state='NEED_CLEAN_MD')
        markdown_correction_needed_len = len(markdown_correction_needed)
        document_nb = 1
        print(f"entries to correct: {markdown_correction_needed_len}")
        for document in markdown_correction_needed:
            progress = round((document_nb / markdown_correction_needed_len) * 100)
            web_doc = WebDocument.get_by_id(session, document['id'])
            if web_doc is None:
                logging.error(f"Document {document['id']} not found")
                continue
            print(
                f"Processing  {web_doc.id} {web_doc.document_type} ({document_nb} from {markdown_correction_needed_len} "
                f"{progress}%): "
                f"{web_doc.url}")
            web_doc.text_md = webpage_text_clean(web_doc.url, web_doc.text_md)
            web_doc.document_state = StalkerDocumentStatus.NEED_MANUAL_REVIEW.name
            session.commit()

        print(f"Step 3 completed in {time.monotonic() - step_start:.1f}s")

        print("\nStep 4: For youtube video setup status ready for translation if transcription is done")
        step_start = time.monotonic()
        if not process_types["youtube"]:
            print("ignoring youtube movies translation for transcription done")
        else:
            transcirption_done = websites.get_transcription_done()
            transcirption_done_len = len(transcirption_done)
            website_nb = 1
            print(f"entries to correct: {transcirption_done_len}")
            for website_id in transcirption_done:
                progress = round((website_nb / transcirption_done_len) * 100)
                web_doc = WebDocument.get_by_id(session, website_id)
                if web_doc is None:
                    logging.error(f"Document {website_id} not found")
                    continue
                print(f"Processing  {web_doc.id} {web_doc.document_type} ({website_nb} from {transcirption_done_len} "
                      f"{progress}%): "
                      f"{web_doc.url}")
                web_doc.document_state = StalkerDocumentStatus.READY_FOR_EMBEDDING.name
                session.commit()
                website_nb += 1

        print(f"Step 4 completed in {time.monotonic() - step_start:.1f}s")

        print(f"\nStep 5: adding embeddings (model: {cfg.get('EMBEDDING_MODEL')})")
        step_start = time.monotonic()
        embedding_needed = websites.get_documents_needing_embedding(cfg.get('EMBEDDING_MODEL'))
        embedding_needed_len = len(embedding_needed)
        print(f"entries to analyze: {embedding_needed_len}")
        website_nb = 1
        model = cfg.get('EMBEDDING_MODEL')
        search_service = SearchService(session)
        for website_id in embedding_needed:
            doc = WebDocument.get_by_id(session, website_id)
            if doc is None:
                logging.error(f"Document {website_id} not found")
                continue
            progress = round((website_nb / embedding_needed_len) * 100)
            print(f"Working on ID:{doc.id} ({website_nb} from {embedding_needed_len} {progress}%)"
                  f" {doc.document_type} url: {doc.url}")

            # Build text for embedding (same logic as StalkerWebDocumentDB.embedding_add)
            if doc.document_type == StalkerDocumentType.link.name:
                text = doc.title or ""
                if doc.summary:
                    text = (text + " " + doc.summary).strip() if text else doc.summary
            else:
                print(f"WARNING: embedding_add not yet implemented for document type: {doc.document_type}, skipping")
                website_nb += 1
                continue

            if not text:
                print(f"WARNING: document {doc.id} has no title or summary, skipping")
                website_nb += 1
                continue

            websites.embedding_delete(doc.id, model)
            result = search_service.get_embedding(text)
            websites.embedding_add(doc.id, result.embedding, doc.language, text, text, model)
            doc.document_state = StalkerDocumentStatus.EMBEDDING_EXIST.name
            session.commit()
            website_nb += 1

        print(f"Step 5 completed in {time.monotonic() - step_start:.1f}s")

        print("\nStep 6: adding missing markdown entries")
        step_start = time.monotonic()
        if missing_markdown_correct:
            from library.website.website_download_context import download_raw_html
            # TODO: sprawdzić, dlaczego jest problem z pobraniem poniższych stron
            problems = [38, 89, 150, 157, 191, 208, 220, 311, 371, 376, 396,
                        443, 456, 465, 470, 486, 497, 499, 503, 531, 553, 581, 592, 600, 601, 602, 611, 662,
                        664, 668, 686, 694, 1013, 6735, 6863, 6878, 6883, 6904, 6913, 6918, 6923, 6926, 6930, 7025]

            # 611 certificate expired
            # problems = []

            document_id_start = max(problems) if len(problems) > 0 else 0
            md_needed = websites.get_documents_md_needed(min_id=document_id_start)
            print(md_needed)

            s3_client = boto3.client('s3')

            for document_id in md_needed:
                web_doc = WebDocument.get_by_id(session, document_id)
                if web_doc is None:
                    logging.error(f"Document {document_id} not found")
                    continue

                if web_doc.paywall:
                    print("Need manual download")
                    continue

                if web_doc.id in problems:
                    print(f"Skipping problem on {document_id}")
                    continue

                print(f"Downloading {web_doc.id} {web_doc.url}, md len({len(web_doc.text_md or '')})")

                html = download_raw_html(url=web_doc.url)
                if not html:
                    print("empty response! [ERROR]")
                    web_doc.document_state = StalkerDocumentStatus.ERROR.name
                    web_doc.document_state_error = StalkerDocumentStatusError.ERROR_DOWNLOAD.name
                    session.commit()
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
                    s3_client.put_object(Bucket=cfg.get("AWS_S3_WEBSITE_CONTENT"), Key=file_name, Body=html)
                    print(f"Successfully uploaded {file_name} to {cfg.get('AWS_S3_WEBSITE_CONTENT')}")
                except Exception as e:
                    error_message = f"Failed to upload {file_name} to {cfg.get('AWS_S3_WEBSITE_CONTENT')}: {str(e)}"
                    print(error_message)
                    continue

                doc_cache_dir = os.path.join(cache_dir, str(s3_uuid))
                os.makedirs(doc_cache_dir, exist_ok=True)
                page_file = os.path.join(doc_cache_dir, f"{s3_uuid}.html")
                with open(page_file, 'w', encoding="utf-8") as file:
                    file.write(html)

                from markitdown import MarkItDown
                md = MarkItDown()
                result = md.convert(page_file)

                md_file = os.path.join(doc_cache_dir, f"{s3_uuid}.md")
                with open(md_file, 'w', encoding="utf-8") as file:
                    file.write(result.text_content)

                md_clean_file = os.path.join(doc_cache_dir, f"{s3_uuid}_clean.md")
                md_cleaned = result.text_content

                # md_cleaned = webpage_text_clean(web_doc.url, md_cleaned)
                web_doc.text_md = md_cleaned
                web_doc.s3_uuid = s3_uuid

                session.commit()

        print(f"Step 6 completed in {time.monotonic() - step_start:.1f}s")

        print(f"\nAll done in {time.monotonic() - script_start:.1f}s, exiting with status 0")
    finally:
        session.close()
