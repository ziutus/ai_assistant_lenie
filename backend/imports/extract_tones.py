#!/usr/bin/env python3
"""Classify the emotional tone and language register of a document, per reader chapter.

Examples from backend/:
    PYTHONPATH=. .venv/bin/python imports/extract_tones.py --id 9144 --dry-run
    PYTHONPATH=. .venv/bin/python imports/extract_tones.py --id 9204 --chapter 37
"""

import argparse
import json
import sys

from library.config_loader import load_config

cfg = load_config()  # noqa: F841 - populates configuration for DB and LLM clients

from library.db.engine import get_session  # noqa: E402
from library.db.models import WebDocument  # noqa: E402
from library.tones import extract_document_tones, refresh_document_tones  # noqa: E402


def _configure_stdout_utf8() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    _configure_stdout_utf8()
    parser = argparse.ArgumentParser(description="Classify the emotional tone of a document's chapters.")
    parser.add_argument("--id", type=int, required=True, help="Document id")
    parser.add_argument("--chapter", type=int, help="Process only one 1-based reader chapter")
    parser.add_argument("--dry-run", action="store_true", help="Do not replace stored tones")
    parser.add_argument("--model", help="LLM model; defaults to TONE_MODEL or Bielik")
    args = parser.parse_args()

    session = get_session()
    try:
        doc = session.get(WebDocument, args.id)
        if doc is None:
            raise SystemExit(f"Document {args.id} not found")
        if args.dry_run:
            result = extract_document_tones(session, doc, args.model, chapter_position=args.chapter)
        else:
            result = refresh_document_tones(session, doc, args.model, chapter_position=args.chapter)
            session.commit()

        for report in result["chapters"]:
            output = {"document_id": doc.id, "model": result["model"], "dry_run": args.dry_run, **report}
            output["tone"] = next(
                (tone for tone in result["tones"] if tone["chapter_position"] == report["chapter_position"]),
                None,
            )
            print(json.dumps(output, ensure_ascii=False))
        return 0
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
