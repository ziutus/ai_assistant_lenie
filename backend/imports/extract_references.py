#!/usr/bin/env python3
"""Extract book footnotes from text_md into document_references (library/references.py).

Removes footnote lines ("¹⁸ https://... (dostęp: ...)", "29 Eurostat.") from
the document's text_md and stores them as structured rows the reader renders
as a per-chapter "Przypisy" section. Replace semantics — safe to re-run.

After --apply, re-run NER for the document (POST /website_entities or the
analysis pipeline) so entities are rebuilt from the cleaned text.

Usage:
    cd backend
    python imports/extract_references.py --id 9204           # dry-run (default)
    python imports/extract_references.py --id 9204 --apply
"""

import argparse
import logging

from library.config_loader import load_config

cfg = load_config()  # noqa: F841 — side effect: populates os.environ for library modules

from library.db.engine import get_session  # noqa: E402
from library.db.models import WebDocument  # noqa: E402
from library.references import extract_footnotes, refresh_document_references  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Extract book footnotes into document_references.")
    parser.add_argument("--id", type=int, required=True, help="Document id")
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry-run)")
    parser.add_argument("--show", type=int, default=15, help="Footnotes to print in dry-run (default: 15)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    session = get_session()
    try:
        doc = session.get(WebDocument, args.id)
        if doc is None or not (doc.text_md or "").strip():
            raise SystemExit(f"Document {args.id} not found or has no text_md")

        if args.apply:
            rows = refresh_document_references(session, doc)
            session.commit()
            with_url = sum(1 for r in rows if r.url)
            logging.info("Saved %d references (%d with URL), text_md updated.", len(rows), with_url)
            logging.info("Re-run NER now (POST /website_entities) to rebuild entities from clean text.")
        else:
            clean, footnotes = extract_footnotes(doc.text_md)
            logging.info("Would extract %d footnotes; text_md %d -> %d chars",
                         len(footnotes), len(doc.text_md), len(clean))
            for fn in footnotes[:args.show]:
                url = f" | url={fn['url']}" if fn["url"] else ""
                logging.info("  [%s] %s%s", fn["marker"], fn["text"][:90], url)
            if len(footnotes) > args.show:
                logging.info("  ... i %d więcej (dry-run — użyj --apply)", len(footnotes) - args.show)
    finally:
        session.close()


if __name__ == "__main__":
    main()
