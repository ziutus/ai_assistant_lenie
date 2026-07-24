#!/usr/bin/env python3
"""Select which control questions a document actually answers (cheap Bielik router).

Examples from backend/:
    PYTHONPATH=. .venv/bin/python imports/select_control_questions.py --id 9204 --dry-run
    PYTHONPATH=. .venv/bin/python imports/select_control_questions.py --id 9204 --chapter 37
"""

import argparse
import json
import sys

from library.config_loader import load_config

cfg = load_config()  # noqa: F841 - populates configuration for DB and LLM clients

from library.control_question_selection import (  # noqa: E402
    extract_document_control_answers,
    refresh_document_control_answers,
)
from library.db.engine import get_session  # noqa: E402
from library.db.models import Document  # noqa: E402


def _configure_stdout_utf8() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    _configure_stdout_utf8()
    parser = argparse.ArgumentParser(description="Select control questions a document actually answers.")
    parser.add_argument("--id", type=int, required=True, help="Document id")
    parser.add_argument("--chapter", type=int, help="Process only one 1-based reader chapter")
    parser.add_argument("--dry-run", action="store_true", help="Do not replace stored answers")
    parser.add_argument("--model", help="LLM model; defaults to CONTROL_QUESTIONS_MODEL or Bielik")
    args = parser.parse_args()

    session = get_session()
    try:
        doc = session.get(Document, args.id)
        if doc is None:
            raise SystemExit(f"Document {args.id} not found")
        if args.dry_run:
            result = extract_document_control_answers(session, doc, args.model, chapter_position=args.chapter)
        else:
            result = refresh_document_control_answers(session, doc, args.model, chapter_position=args.chapter)
            session.commit()

        if not result["chapters"]:
            print(json.dumps({
                "document_id": doc.id, "model": result["model"], "dry_run": args.dry_run,
                "message": "no candidate control questions for this document's tags",
            }, ensure_ascii=False))
            return 0

        for report in result["chapters"]:
            output = {"document_id": doc.id, "model": result["model"], "dry_run": args.dry_run, **report}
            output["selected"] = [
                a for a in result["answers"] if a["chapter_position"] == report["chapter_position"]
            ]
            print(json.dumps(output, ensure_ascii=False))
        return 0
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
