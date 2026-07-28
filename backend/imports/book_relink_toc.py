#!/usr/bin/env python3
"""One-off backfill: apply library.book_pdf_import.link_toc_entries() to a
book already imported before that function existed.

The book's own printed "SPIS TREŚCI" page was extracted as plain dot-leader
prose ("Tytuł . . . . . . 19") that reads as one unbroken wall of text in the
reader (see build_book_markdown()'s docstring). link_toc_entries() is a pure
text -> text transform — no PDF re-extraction needed — so this backfill just
loads the document's existing text_md, runs it through the same function new
imports get automatically, and writes it back. Replace semantics, safe to
re-run on a document it hasn't touched yet; already-processed documents
(text_md already containing a "[#toc-" anchor) are skipped by default since
running it twice would stack a second, redundant anchor in front of every
header — pass --force to re-run anyway.

Usage:
    cd backend
    .venv/Scripts/python imports/book_relink_toc.py --id 9339             # dry-run (default)
    .venv/Scripts/python imports/book_relink_toc.py --id 9339 --apply
    .venv/Scripts/python imports/book_relink_toc.py --id 9339 --apply --force  # re-run anyway
"""

import argparse
import logging

from library.config_loader import load_config

cfg = load_config()  # noqa: F841 — side effect: populates os.environ for library modules

from library.book_pdf_import import link_toc_entries  # noqa: E402
from library.db.engine import get_session  # noqa: E402
from library.db.models import Document  # noqa: E402

logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Backfill: link SPIS TREŚCI entries in an already-imported book.")
    parser.add_argument("--id", type=int, required=True, help="Document id of the already-imported book")
    parser.add_argument("--apply", action="store_true", help="Write changes to the database (default: dry-run)")
    parser.add_argument("--force", action="store_true", help="Re-run even if text_md already has [#toc- anchors")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    session = get_session()
    try:
        doc = session.get(Document, args.id)
        if doc is None:
            raise SystemExit(f"Document {args.id} not found")
        if not doc.text_md:
            raise SystemExit(f"Document {args.id} has no text_md")
        if "[#toc-" in doc.text_md and not args.force:
            raise SystemExit(
                f"Document {args.id} already has [#toc- anchors — looks already processed. "
                "Pass --force to re-run anyway."
            )

        new_text = link_toc_entries(doc.text_md)
        changed = new_text != doc.text_md
        logging.info(
            "doc #%s: %s (old %d chars, new %d chars, %d new anchors)",
            args.id,
            "would change" if changed else "no change",
            len(doc.text_md),
            len(new_text),
            new_text.count("[#toc-"),
        )

        if args.apply:
            doc.text_md = new_text
            session.commit()
            logging.info("Saved.")
        else:
            logging.info("Dry-run — nothing written. Re-run with --apply to save.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
