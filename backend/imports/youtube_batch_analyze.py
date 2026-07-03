#!/usr/bin/env python3
"""
Batch analysis of long YouTube transcripts using Bielik LLM via CloudFerro Sherlock.

The LLM pipeline (chunk splitting, speaker extraction/labeling, two-pass
rewrite + summarize, topic grouping, synthesis, DB persistence) lives in
library/document_analysis_service.py + library/chunk_llm_analysis.py and is
shared with the Flask API (chunk_review_routes.py). File exports live in
library/analysis_exports.py. This script is a thin CLI on top of them, adding:
  - dry-run preview (chunk breakdown + cost estimate, no API calls)
  - explicit --speaker1/--speaker2 override (skips LLM speaker extraction)

For a brand-new video, use imports/youtube_add.py <URL> --analyze instead —
it adds the document and runs this analysis in one go.

Cost at 0.56 EUR/M tokens: ~0.05 EUR for a 90K-char transcript
  (19 chunks × ~4,700 tok/chunk = 89K tokens).

Usage (from backend/ directory):
    # Windows PowerShell
    $env:PYTHONPATH="."; $env:PYTHONIOENCODING="utf-8"; .venv/Scripts/python imports/youtube_batch_analyze.py --doc_id 9158
    $env:PYTHONPATH="."; $env:PYTHONIOENCODING="utf-8"; .venv/Scripts/python imports/youtube_batch_analyze.py --doc_id 9158 --dry_run
    $env:PYTHONPATH="."; $env:PYTHONIOENCODING="utf-8"; .venv/Scripts/python imports/youtube_batch_analyze.py --doc_id 9158 --no_synthesis

    # WSL / Linux (Bash)
    PYTHONPATH=. .venv/bin/python imports/youtube_batch_analyze.py --doc_id 9158
"""

import argparse
import re
import sys

from library.config_loader import load_config

load_config()

from library.analysis_exports import export_analysis_run  # noqa: E402
from library.chunk_llm_analysis import assign_speakers, remove_speech_fillers  # noqa: E402
from library.db.engine import get_session  # noqa: E402
from library.db.models import WebDocument  # noqa: E402
from library.document_analysis_service import (  # noqa: E402
    ANALYSIS_MODELS,
    CHUNK_CHARS,
    DEFAULT_ANALYSIS_MODEL,
    DocumentAnalysisService,
    _extract_text,
    _load_segments,
)
from library.text_functions import split_text_into_sentence_chunks  # noqa: E402


def main():
    parser = argparse.ArgumentParser(
        description="YouTube transcript: correct + segment + summarize (Bielik LLM)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--doc_id", type=int, required=True,
                        help="Document ID in the database")
    parser.add_argument("--model", default=DEFAULT_ANALYSIS_MODEL,
                        choices=ANALYSIS_MODELS,
                        help="Model to use")
    parser.add_argument("--chunk_size", type=int, default=CHUNK_CHARS,
                        help="Characters per chunk (≈1,500 tokens at default 5,000)")
    parser.add_argument("--speaker1", default="",
                        help="Name of first speaker (segments before first >>). "
                             "If omitted, speakers are auto-extracted via LLM.")
    parser.add_argument("--speaker2", default="",
                        help="Name of second speaker (segments after first >>).")
    parser.add_argument("--no_synthesis", action="store_true",
                        help="Skip final synthesis step")
    parser.add_argument("--dry_run", action="store_true",
                        help="Show chunk breakdown without calling the API")
    args = parser.parse_args()

    print(f"Pobieranie dokumentu {args.doc_id}...")
    session = get_session()
    try:
        doc = WebDocument.get_by_id(session, args.doc_id)
        if doc is None:
            print(f"BŁĄD: Dokument {args.doc_id} nie znaleziony.")
            sys.exit(1)

        print(f"Tytuł  : {doc.title}")
        print(f"Typ    : {doc.document_type} | Stan: {doc.document_state}")
        if doc.author:
            print(f"Autor  : {doc.author}")

        segments = _load_segments(getattr(doc, "text_raw", "") or "")
        if segments:
            print(f"Segm.  : {len(segments)} segmentów z timestampami w text_raw")
        else:
            print("Segm.  : brak JSON w text_raw — widok HTML bez linków YT")

        text, text_field = _extract_text(doc)
        if not text:
            print("BŁĄD: Brak tekstu w polach text / text_raw / text_md.")
            sys.exit(1)

        speaker_changes = len(re.findall(r">>", text))
        if speaker_changes:
            print(f"Format : Rozmowa ({speaker_changes} zmian mówcy)")
        else:
            print("Format : Monolog (brak znaczników >>)")
        print(f"Tekst  : pole '{text_field}', {len(text):,} znaków")

        speakers_override = None
        if args.speaker1 and args.speaker2:
            speakers_override = [
                {"name": args.speaker1, "role": "prowadzący", "description": ""},
                {"name": args.speaker2, "role": "gość", "description": ""},
            ]

        if args.dry_run:
            preview_text = text
            if speaker_changes and speakers_override:
                preview_text = assign_speakers(preview_text, args.speaker1, args.speaker2)
            cleaned_text = remove_speech_fillers(preview_text)
            chunks = split_text_into_sentence_chunks(cleaned_text, args.chunk_size)
            est_tokens_total = len(chunks) * (args.chunk_size // 3 * 2)  # rough: in+out
            est_cost = est_tokens_total / 1_000_000 * 0.56
            print(f"\nPodział: {len(chunks)} fragmentów po max {args.chunk_size:,} znaków")
            print(f"Szacowany koszt: ~{est_tokens_total:,} tokenów ≈ {est_cost:.3f} EUR\n")
            for i, ch in enumerate(chunks):
                print(f"  [{i + 1:>2}] {len(ch):>6,} znaków")
            print("\n[dry_run] Tryb podglądu — API nie zostało wywołane.")
            return

        print(f"\n=== PRZETWARZANIE → {args.model} (DocumentAnalysisService) ===\n")
        service = DocumentAnalysisService(session)
        run = service.create_run(
            doc_id=args.doc_id,
            model=args.model,
            chunk_size=args.chunk_size,
            no_synthesis=args.no_synthesis,
            progress_fn=lambda msg: print(f"  {msg}", flush=True),
            speakers=speakers_override,
        )

        run_id = run.id
        exports = export_analysis_run(doc, run, args.model)
        print(f"\n{exports['toc']}\n")
    finally:
        session.close()

    print(f"\n✓ Analiza (MD):  {exports['md']}")
    print(f"✓ Dane (JSON):   {exports['json']}")
    print(f"✓ Debug (MD):    {exports['debug']}")
    if exports["html"]:
        print(f"✓ Widok HTML:    {exports['html']}")
    print(f"✓ DB Run ID:     {run_id}")


if __name__ == "__main__":
    main()
