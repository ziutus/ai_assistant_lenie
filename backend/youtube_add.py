#!/usr/bin/env python3
"""CLI script for ad-hoc YouTube video processing.

Usage:
    python youtube_add.py <URL> [--language pl] [--note "..."] [--source own] [--chapters "..."] [--summary] [--force] [-v]
"""

import argparse
import logging
import sys
import time

from dotenv import load_dotenv

load_dotenv()

from library.youtube_processing import process_youtube_url


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

    try:
        web_document = process_youtube_url(
            youtube_url=args.url,
            language=args.language,
            chapter_list=chapter_list,
            note=args.note,
            source=args.source,
            ai_summary_needed=args.summary,
            force_reprocess=args.force,
        )
    except Exception as e:
        logging.error(f"Error processing YouTube URL: {e}")
        sys.exit(1)

    # Print summary
    print("\n--- Document Summary ---")
    print(f"  ID:       {web_document.id}")
    print(f"  Title:    {web_document.title}")
    print(f"  URL:      {web_document.url}")
    print(f"  Language: {web_document.language}")
    print(f"  Status:   {web_document.document_state}")
    text_len = len(web_document.text) if web_document.text else 0
    print(f"  Text length: {text_len} characters")
    if web_document.summary:
        print(f"  Summary:  {web_document.summary[:200]}...")
    elapsed = time.time() - t_start
    print(f"  Elapsed:  {elapsed:.2f}s")
    print("------------------------")


if __name__ == "__main__":
    main()
