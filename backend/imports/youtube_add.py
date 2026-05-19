#!/usr/bin/env python3
"""CLI script for ad-hoc YouTube video processing.

Usage:
    python youtube_add.py <URL> [--language pl] [--note "..."] [--source own] [--chapters "..."] [--summary] [--force] [-v]
"""

import argparse
import logging
import sys
import time

from library.config_loader import load_config

cfg = load_config()  # noqa: F841 — side effect: populates os.environ for library modules

from library.db.engine import get_session  # noqa: E402
from library.youtube_processing import process_youtube_url  # noqa: E402


def main():
    parser = argparse.ArgumentParser(
        description="Process a YouTube video: add to database, fetch metadata, download captions/transcription."
    )
    parser.add_argument("url", help="YouTube video URL")
    parser.add_argument("--language", help="Language code (e.g. pl, en)")
    parser.add_argument("--note", help="Note to attach to the document")
    parser.add_argument("--source", default="own", help="Source identifier (default: own)")
    parser.add_argument("--chapters", help="Chapter list as text")
    parser.add_argument("--chapters-file", help="Path to file with chapter list")
    parser.add_argument("--summary", action="store_true", help="Generate AI summary")
    parser.add_argument("--force", action="store_true", help="Force reprocessing even if embeddings exist")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    chapter_list = args.chapters
    if args.chapters_file:
        try:
            with open(args.chapters_file, 'r', encoding='utf-8') as f:
                chapter_list = f.read()
        except FileNotFoundError:
            print(f"Error: chapters file not found: {args.chapters_file}")
            sys.exit(1)

    t_start = time.time()
    logging.info("Script started")

    webshare_api_key = cfg.get("WEBSHARE_API_KEY")
    if webshare_api_key:
        try:
            from library.webshare_ip_auth import ensure_ip_authorized, check_bandwidth
            ensure_ip_authorized(webshare_api_key)
            bw = check_bandwidth(webshare_api_key)
            if not bw["available"]:
                logging.warning("Webshare bandwidth exhausted — proxy disabled")
                webshare_api_key = None
        except Exception as e:
            logging.warning(f"Webshare IP auth failed: {e} — proceeding without proxy")
            webshare_api_key = None

    session = get_session()
    try:
        web_document = process_youtube_url(
            session=session,
            youtube_url=args.url,
            language=args.language,
            chapter_list=chapter_list,
            note=args.note,
            source=args.source,
            ai_summary_needed=args.summary,
            force_reprocess=args.force,
            webshare_api_key=webshare_api_key,
        )

        # Collect attributes while session is still open
        elapsed = time.time() - t_start
        doc_id = web_document.id
        doc_title = web_document.title
        doc_url = web_document.url
        doc_language = web_document.language
        doc_state = web_document.document_state
        doc_text_len = len(web_document.text) if web_document.text else 0
        doc_summary = web_document.summary
    except Exception as e:
        logging.error(f"Error processing YouTube URL: {e}")
        sys.exit(1)
    finally:
        session.close()

    # Print summary
    print("\n--- Document Summary ---")
    print(f"  ID:       {doc_id}")
    print(f"  Title:    {doc_title}")
    print(f"  URL:      {doc_url}")
    print(f"  Language: {doc_language}")
    print(f"  Status:   {doc_state}")
    print(f"  Text length: {doc_text_len} characters")
    if doc_summary:
        print(f"  Summary:  {doc_summary[:200]}...")
    print(f"  Elapsed:  {elapsed:.2f}s")
    print("------------------------")


if __name__ == "__main__":
    main()
