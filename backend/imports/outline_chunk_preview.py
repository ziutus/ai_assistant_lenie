"""Read-only REST preview of transcript chunks derived from an approved outline."""

import argparse
import os
import re
from unittest.mock import patch

import requests

from library.document_analysis_service import CHUNK_CHARS, _chapter_chunks_from_text
from library.outline_boundaries import (
    insert_topic_headings,
    locate_topic_starts,
    merge_small_chunks,
    parse_outline_topics,
)
from library.text_functions import split_text_into_sentence_chunks


def _read_only_llm(**kwargs):
    """Use the provider router without its otherwise automatic DB usage writes.

    This scoped patch is only for this single-threaded diagnostic process.
    Neither the normal router nor the analysis pipeline is changed.
    """
    from library.ai import ai_ask

    with patch("library.ai._record_usage", return_value=None):
        return ai_ask(**kwargs)


def _show(label: str, chunks: list[str]) -> None:
    print(f"\n{label}: {len(chunks)} chunks; lengths: {[len(chunk) for chunk in chunks]}")
    for index, chunk in enumerate(chunks, 1):
        compact = re.sub(r"\s+", " ", chunk).strip()
        print(f"[{index:2}] {len(chunk):5} chars | START: {compact[:100]}")
        print(f"                 END: {compact[-80:]}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("id", type=int, help="YouTube document ID")
    parser.add_argument("--base-url", default="http://192.168.200.7:5055")
    parser.add_argument("--chunk-size", type=int, default=CHUNK_CHARS)
    args = parser.parse_args(argv)
    api_key = os.environ.get("LENIE_API_KEY")
    if not api_key:
        parser.error("LENIE_API_KEY must be set")
    if args.id <= 0 or args.chunk_size <= 0:
        parser.error("Document ID and chunk size must be positive")
    try:
        response = requests.get(
            f"{args.base_url.rstrip('/')}/website_get", params={"id": args.id},
            headers={"x-api-key": api_key}, timeout=60, allow_redirects=False,
        )
        response.raise_for_status()
        if response.status_code != 200:
            raise ValueError(f"Unexpected HTTP status: {response.status_code}")
        doc = response.json()
        if not isinstance(doc, dict) or doc.get("document_type") != "youtube":
            raise ValueError("Document must have document_type youtube")
        for field in ("text", "outline_md"):
            if not isinstance(doc.get(field), str) or not doc[field].strip():
                raise ValueError(f"Document must have non-empty {field}")
        if doc.get("chapter_list"):
            raise ValueError("This preview is for transcripts without chapter_list")
        topics = parse_outline_topics(doc["outline_md"])
        if not topics:
            raise ValueError("Outline must contain ### topic headings")
        text = doc["text"]
        _show("Old (size-based)", split_text_into_sentence_chunks(text, args.chunk_size))
        starts = locate_topic_starts(text, topics, llm=_read_only_llm)
        for topic, offset in zip(topics, starts):
            print(f"Topic: {topic['title']} | start: {offset if offset is not None else 'DROPPED'}")
        titles = [topic["title"] for topic in topics]
        marked = insert_topic_headings(text, starts, titles)
        retained_titles = [title for title, start in zip(titles, starts) if start is not None]
        chunks = _chapter_chunks_from_text(marked, retained_titles, args.chunk_size)
        if chunks is None:
            raise ValueError("No usable outline boundaries; cannot produce an outline-based preview")
        _show("New (outline-based)", merge_small_chunks(chunks, max_chars=args.chunk_size))
    except (requests.RequestException, ValueError) as exc:
        parser.exit(1, f"Preview failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
