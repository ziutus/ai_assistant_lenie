#!/usr/bin/env python3
"""Extract a document timeline with optional single-chapter dry-run.

Examples from backend/:
    PYTHONPATH=. .venv/bin/python imports/extract_events.py --id 9204 --chapter 37 --dry-run
    PYTHONPATH=. .venv/bin/python imports/extract_events.py --id 9204
"""

import argparse
import json
import sys

from library.config_loader import load_config

cfg = load_config()  # noqa: F841 - populates configuration for DB and LLM clients

from library.db.engine import get_session  # noqa: E402
from library.db.models import Document  # noqa: E402
from library.timeline_events import extract_document_events, refresh_document_events  # noqa: E402


def _json_default(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _configure_stdout_utf8() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    _configure_stdout_utf8()
    parser = argparse.ArgumentParser(description="Extract dated events discussed in a document.")
    parser.add_argument("--id", type=int, required=True, help="Document id")
    parser.add_argument("--chapter", type=int, help="Process only one 1-based reader chapter")
    parser.add_argument("--dry-run", action="store_true", help="Do not replace stored events")
    parser.add_argument("--model", help="LLM model; defaults to TIMELINE_MODEL or Bielik")
    args = parser.parse_args()

    session = get_session()
    try:
        doc = session.get(Document, args.id)
        if doc is None:
            raise SystemExit(f"Document {args.id} not found")
        if args.dry_run:
            result = extract_document_events(session, doc, args.model, chapter_position=args.chapter)
        else:
            result = refresh_document_events(session, doc, args.model, chapter_position=args.chapter)
            session.commit()

        for report in result["chapters"]:
            output = {"document_id": doc.id, "model": result["model"], "dry_run": args.dry_run, **report}
            if args.dry_run:
                output["event_list"] = [
                    event
                    for event in result["events"]
                    if event["chapter_position"] == report["chapter_position"]
                ]
            print(json.dumps(output, ensure_ascii=False, default=_json_default))
        return 0
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
