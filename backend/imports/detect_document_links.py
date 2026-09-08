#!/usr/bin/env python3
"""Backfill: propose `references` document links from verbatim URL mentions.

For every document (or one `--id`), scan its text for URLs that resolve to
another document already in the library and create a `proposed`
``document_links`` row (``detection_method='url_mention'``). Idempotent — an
edge that already exists in any status is left untouched. Nothing is
confirmed automatically; accept proposals via ``PATCH /document_links/<id>``
or the "Powiązane dokumenty" panel in the editor.

Usage:
    cd backend
    .venv/Scripts/python imports/detect_document_links.py            # dry-run
    .venv/Scripts/python imports/detect_document_links.py --apply
    .venv/Scripts/python imports/detect_document_links.py --id 10477 --apply
"""

import argparse
import logging

from library.config_loader import load_config

cfg = load_config()  # noqa: F841 — side effect: populates os.environ for library modules

from library.db.engine import get_session  # noqa: E402
from library.db.models import Document  # noqa: E402
from library.document_links_service import detect_url_mention_links  # noqa: E402

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", type=int, help="only this document id")
    parser.add_argument("--apply", action="store_true", help="commit (default: dry-run)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    session = get_session()
    try:
        if args.id:
            ids = [args.id]
        else:
            ids = [row[0] for row in session.query(Document.id).order_by(Document.id).all()]

        total = 0
        for doc_id in ids:
            created = detect_url_mention_links(session, doc_id, commit=False)
            for link in created:
                other = session.get(Document, link.to_document_id)
                logger.info(
                    "doc %s -> references -> doc %s (%s)",
                    doc_id, link.to_document_id, (other.url if other else "?"),
                )
            total += len(created)
            if not args.apply:
                session.rollback()

        if args.apply:
            session.commit()
            logger.info("committed %s proposed link(s)", total)
        else:
            logger.info("dry-run: would propose %s link(s) (use --apply)", total)
    finally:
        session.close()


if __name__ == "__main__":
    main()
