"""Read-only REST preview of transcript chunks derived from an approved outline."""

import argparse
import json
import os
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import requests

from library.document_analysis_service import CHUNK_CHARS, _chapter_chunks_from_text
from library.outline_boundaries import (
    anchors_to_starts,
    build_anchor_payload,
    insert_topic_headings,
    locate_topic_starts,
    merge_small_chunks,
    parse_outline_topics,
)
from library.chunk_llm_analysis import remove_speech_fillers
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
    parser.add_argument("--quotes", type=Path, help="Session-model starts JSON; skip all LLM calls")
    parser.add_argument("--emit-anchors", action="store_true", help="Print payload JSON to stdout; preview to stderr")
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
        # Match production step 7, which receives filler-cleaned text.
        text = remove_speech_fillers(doc["text"])
        payload = None
        if args.quotes:
            quotes = json.loads(args.quotes.read_text(encoding="utf-8-sig"))
            payload = build_anchor_payload(doc["text"], doc["outline_md"], quotes)
        else:
            collected = [set() for _ in topics]

            def capture_llm(**kwargs):
                response = _read_only_llm(**kwargs)
                data = json.loads(response if isinstance(response, str) else response.response_text)
                if not isinstance(data, dict) or not isinstance(data.get("starts"), list):
                    raise ValueError("Expected an object with a starts array from the boundary locator")
                for item in data.get("starts", []):
                    if not isinstance(item, dict):
                        continue
                    index, sentence = item.get("id"), item.get("sentence")
                    if (type(index) is int and 0 <= index < len(topics)
                            and isinstance(sentence, str) and sentence.strip()):
                        collected[index].add(sentence)
                return response

            starts = locate_topic_starts(
                doc["text"] if args.emit_anchors else text, topics,
                llm=capture_llm if args.emit_anchors else _read_only_llm,
            )
            if args.emit_anchors:
                quotes = {"starts": [{"id": i, "sentence": next(iter(values)) if len(values) == 1 else None}
                                     for i, values in enumerate(collected)]}
                payload = build_anchor_payload(doc["text"], doc["outline_md"], quotes)
        with redirect_stdout(sys.stderr if args.emit_anchors else sys.stdout):
            _show("Old (size-based)", split_text_into_sentence_chunks(text, args.chunk_size))
            if payload is not None:
                kept = {(a["title"], a["sentence"]) for a in payload["anchors"]}
                for i, topic in enumerate(topics):
                    sentence = next((q["sentence"] for q in quotes["starts"] if q["id"] == i), None)
                    if (topic["title"], sentence) not in kept:
                        print(f"Topic: {topic['title']} | start: DROPPED")
                topics = payload["anchors"]
                starts = anchors_to_starts(text, topics)
            for topic, offset in zip(topics, starts):
                print(f"Topic: {topic['title']} | start: {offset if offset is not None else 'DROPPED'}")
            titles = [topic["title"] for topic in topics]
            retained_titles = [title for title, start in zip(titles, starts) if start is not None]
            if len(retained_titles) < 2:
                print("Fewer than 2 topics located; production will use the size-based split.")
                chunks = split_text_into_sentence_chunks(text, args.chunk_size)
            else:
                marked = insert_topic_headings(text, starts, titles)
                chunks = _chapter_chunks_from_text(marked, retained_titles, args.chunk_size)
                if chunks is None:
                    raise ValueError("No usable outline boundaries; cannot produce an outline-based preview")
                chunks = merge_small_chunks(chunks, max_chars=args.chunk_size)
            _show("New (outline-based)", chunks)
        if args.emit_anchors:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
    except (requests.RequestException, ValueError, OSError) as exc:
        parser.exit(1, f"Preview failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
