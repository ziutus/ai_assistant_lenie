#!/usr/bin/env python3
"""CLI script for ad-hoc YouTube video processing.

Usage:
    python youtube_add.py <URL> [--language pl] [--note "..."] [--source own] [--chapters "..."] [--summary] [--force] [-v]
    python youtube_add.py <URL> --analyze [--model ...] [--speaker1 "..." --speaker2 "..."] [--no-synthesis]

With --analyze, after the video is added and transcribed, the Bielik LLM chunk
analysis (library/document_analysis_service.py) runs on the new document and
exports MD/JSON/debug/HTML files to .claude/exports/. To (re-)analyze an
existing document by ID, use imports/youtube_batch_analyze.py instead.
"""

import argparse
import logging
import sys
import time

from library.config_loader import load_config

cfg = load_config()  # noqa: F841 — side effect: populates os.environ for library modules

from library.analysis_exports import export_analysis_run  # noqa: E402
from library.db.engine import get_session  # noqa: E402
from library.document_analysis_service import (  # noqa: E402
    ANALYSIS_MODELS,
    DEFAULT_ANALYSIS_MODEL,
    DocumentAnalysisService,
)
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
    parser.add_argument("--no-proxy", action="store_true", help="Disable Webshare proxy (useful when proxy gets 429 from YouTube)")
    parser.add_argument("--analyze", action="store_true",
                        help="Run Bielik LLM chunk analysis after processing "
                             "(exports MD/JSON/debug/HTML to .claude/exports/)")
    parser.add_argument("--model", default=DEFAULT_ANALYSIS_MODEL, choices=ANALYSIS_MODELS,
                        help="LLM model for --analyze (default: %(default)s)")
    parser.add_argument("--speaker1", default="",
                        help="--analyze: name of first speaker (segments before first >>); "
                             "with --speaker2 skips LLM speaker extraction")
    parser.add_argument("--speaker2", default="", help="--analyze: name of second speaker")
    parser.add_argument("--no-synthesis", action="store_true", help="--analyze: skip final synthesis step")
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

    if args.analyze:
        # Rozgrzej serwis NER w tle — ładowanie modelu spaCy nakłada się na
        # pobieranie/transkrypcję i analizę LLM zamiast blokować krok encji
        from library.ner_client import warmup_async
        warmup_async()

    webshare_api_key = cfg.get("WEBSHARE_API_KEY")
    if args.no_proxy:
        logging.info("--no-proxy flag set — Webshare proxy disabled")
        webshare_api_key = None
    elif webshare_api_key:
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
        doc_state = web_document.processing_status
        doc_text_len = len(web_document.text) if web_document.text else 0
        doc_summary = web_document.summary

        # Optional LLM chunk analysis on the freshly processed document
        run_id = None
        exports = None
        analysis_error = None
        if args.analyze:
            if not web_document.text:
                analysis_error = f"document has no transcript text (state: {doc_state})"
            else:
                speakers_override = None
                if args.speaker1 and args.speaker2:
                    speakers_override = [
                        {"name": args.speaker1, "role": "prowadzący", "description": ""},
                        {"name": args.speaker2, "role": "gość", "description": ""},
                    ]
                print(f"\n=== ANALIZA LLM → {args.model} (DocumentAnalysisService) ===\n")
                try:
                    service = DocumentAnalysisService(session)
                    run = service.create_run(
                        doc_id=doc_id,
                        model=args.model,
                        no_synthesis=args.no_synthesis,
                        progress_fn=lambda msg: print(f"  {msg}", flush=True),
                        speakers=speakers_override,
                    )
                    run_id = run.id
                    exports = export_analysis_run(web_document, run, args.model)
                except Exception as e:
                    logging.error(f"LLM analysis failed: {e}")
                    analysis_error = str(e)
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

    if args.analyze:
        if analysis_error:
            print(f"\nBŁĄD analizy LLM: {analysis_error}")
            print("Dokument został dodany — analizę można powtórzyć:")
            print(f"  python imports/youtube_batch_analyze.py --doc_id {doc_id}")
            sys.exit(1)
        print("\n--- Analiza LLM ---")
        print(f"  Run ID:       {run_id}")
        print(f"  Analiza (MD): {exports['md']}")
        print(f"  Dane (JSON):  {exports['json']}")
        print(f"  Debug (MD):   {exports['debug']}")
        if exports["html"]:
            print(f"  Widok HTML:   {exports['html']}")
        print("-------------------")


if __name__ == "__main__":
    main()
