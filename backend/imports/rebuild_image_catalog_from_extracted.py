#!/usr/bin/env python3
"""One-off backfill: rebuild a missing image catalog from text_extracted.

Older webpage/link documents may already have [imgN] markers in text_md
but no document_images rows. Extract images from the surviving original
markdown snapshot only; never modify text_md or text_extracted and never
fetch source HTML. Refuse documents with an existing URL image catalog or
any analysis runs, chunks, or embeddings: those need a reviewed procedure.

Usage:
    cd backend
    .venv/Scripts/python imports/rebuild_image_catalog_from_extracted.py --id 10482          # dry-run (default)
    .venv/Scripts/python imports/rebuild_image_catalog_from_extracted.py --id 10482 --apply
"""

import argparse
import logging

from library.config_loader import load_config
from library.article_cleaner import extract_inline_images
from library.db.engine import get_session
from library.db.models import Document, DocumentAnalysisRun, DocumentChunk, DocumentEmbedding, DocumentImage
from library.document_images import replace_document_images

logger = logging.getLogger(__name__)

ELIGIBLE_TYPES = ("webpage", "link")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--id", type=int, required=True, help="Process a single document by id")
    parser.add_argument("--apply", action="store_true", help="Write changes to the database (default: dry-run)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s: %(message)s")

    cfg = load_config()  # noqa: F841 — populate configuration after parsing so --help stays offline
    session = get_session()
    try:
        doc = Document.get_by_id(session, args.id)
        if doc is None:
            logging.error("doc #%s not found — refusing", args.id)
            return 1
        if doc.document_type not in ELIGIBLE_TYPES:
            logging.error("doc #%s has document_type=%r, not in %s — refusing", doc.id, doc.document_type, ELIGIBLE_TYPES)
            return 1
        if not doc.text_extracted:
            logging.error("doc #%s has empty text_extracted, nothing to reconstruct from — refusing", doc.id)
            return 1

        image_count = session.query(DocumentImage).filter(
            DocumentImage.document_id == doc.id,
            DocumentImage.storage_key.is_(None),
        ).count()
        if image_count:
            logging.error("doc #%s already has %d URL-sourced document_images rows — refusing", doc.id, image_count)
            return 1

        counts = {
            model.__tablename__: session.query(model).filter(model.document_id == doc.id).count()
            for model in (DocumentAnalysisRun, DocumentChunk, DocumentEmbedding)
        }
        if any(counts.values()):
            logging.error("doc #%s has analysis data (%s); a separate reviewed procedure is required — refusing", doc.id, counts)
            return 1

        _, images = extract_inline_images(doc.text_extracted)
        if not images:
            logging.info("doc #%s: no images found in text_extracted, nothing to do", doc.id)
            return 0

        logging.info("doc #%s (%s): text_extracted length=%d, %d image(s) found", doc.id, doc.title, len(doc.text_extracted), len(images))
        logging.info("Current URL-sourced document_images count (storage_key IS NULL): %d", image_count)
        for img in images:
            logging.info("  - url=%s alt=%r", img["url"], img["alt"])
        logging.info("text_md/text_extracted will NOT be modified by this script.")

        if args.apply:
            rows = replace_document_images(session, doc.id, images)
            session.commit()
            logging.info("Done. Wrote %d document_images rows for doc #%s.", len(rows), doc.id)
        else:
            logging.info("Dry-run: would write %d document_images rows. Re-run with --apply to save.", len(images))
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
