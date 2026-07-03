#!/usr/bin/env python3
"""Regenerate HTML view from existing JSON analysis file (no LLM calls)."""
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unified_config_loader import load_config
from library.db.engine import get_session
from library.db.models import WebDocument

from library.analysis_exports import save_html
from library.document_analysis_service import _load_segments as _load_transcript_segments


def main():
    if len(sys.argv) < 2:
        print("Usage: python _regen_html.py <json_file>")
        sys.exit(1)

    json_path = sys.argv[1]
    if not os.path.exists(json_path):
        print(f"BŁĄD: Nie znaleziono pliku: {json_path}")
        sys.exit(1)

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    meta = data["meta"]
    doc_id = meta["doc_id"]
    title = meta["title"]
    model = meta["model"]
    fmt = meta.get("format", {})
    speaker_info = meta.get("speakers", [])

    sections = [
        {
            "original": c["original"],
            "text": c["corrected"],
            "type": c["type"],
            "topic": c["topic"],
            "ratio": c["ratio"],
            "summary": c["summary"],
        }
        for c in data["chunks"]
    ]

    topic_sections = [
        {
            "title": t["title"],
            "type": t["type"],
            "chunk_indices": t["chunk_indices"],
            "text": "",
            "summary": t["summary"],
        }
        for t in data["topics"]
    ]

    load_config()
    session = get_session()
    doc = WebDocument.get_by_id(session, doc_id)
    if doc is None:
        print(f"BŁĄD: Dokument {doc_id} nie znaleziony.")
        sys.exit(1)

    video_id = getattr(doc, "original_id", "") or ""
    segments = _load_transcript_segments(getattr(doc, "text_raw", "") or "")
    if not segments:
        print("BŁĄD: Brak JSON z timestampami w text_raw.")
        sys.exit(1)

    print(f"Regeneruję HTML dla doc {doc_id}: {title}")
    print(f"Segmentów: {len(segments)}, Sekcji: {len(topic_sections)}, Chunków: {len(sections)}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    html_file = save_html(
        doc_id, title, model,
        topic_sections, sections, segments, video_id,
        timestamp, fmt=fmt, speaker_info=speaker_info,
    )
    print(f"✓ Widok HTML: {html_file}")


if __name__ == "__main__":
    main()
