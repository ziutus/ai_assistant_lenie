#!/usr/bin/env python3
"""Backfill: fill the empty plain text of webpage documents from text_md.

The document_prepare worker used to store only text_md, so views reading the
plain text (e.g. the NER chapter review) saw an empty document until someone
saved it in the editor. This derives text exactly like that save does.
Only text is written: statuses, entities and text_md stay untouched.

Usage:
    cd backend
    .venv/Scripts/python imports/backfill_webpage_text_from_md.py                # dry-run (default)
    .venv/Scripts/python imports/backfill_webpage_text_from_md.py --apply
    .venv/Scripts/python imports/backfill_webpage_text_from_md.py --id 11294 --apply
"""

import argparse
import logging

from library.config_loader import load_config

cfg = load_config()  # noqa: F841 — side effect: populates os.environ for library modules

from sqlalchemy import func  # noqa: E402

from library.db.engine import get_session  # noqa: E402
from library.db.models import Document  # noqa: E402
from library.lenie_markdown import md_remove_markdown  # noqa: E402


def backfill(session, *, apply: bool, doc_id: int | None = None) -> list[int]:
    """Return ids of the documents changed (or, in a dry run, to be changed)."""
    query = session.query(Document).filter(
        Document.document_type == "webpage",
        func.coalesce(func.trim(Document.text), "") == "",
        func.coalesce(func.trim(Document.text_md), "") != "",
    )
    if doc_id is not None:
        query = query.filter(Document.id == doc_id)
    changed = []
    for doc in query.order_by(Document.id).all():
        text = md_remove_markdown(doc.text_md)
        if not text.strip():
            continue
        changed.append(doc.id)
        if apply:
            doc.text = text
    if apply:
        session.commit()
    return changed


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Write changes to the database (default: dry-run)")
    parser.add_argument("--id", type=int, help="Process a single document by id")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    session = get_session()
    try:
        changed = backfill(session, apply=args.apply, doc_id=args.id)
        logging.info("%s %d document(s): %s", "Updated" if args.apply else "Dry-run, would update",
                     len(changed), changed)
    finally:
        session.close()


if __name__ == "__main__":
    main()
