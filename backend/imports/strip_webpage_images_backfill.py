#!/usr/bin/env python3
"""Backfill: strip raw inline images out of text_md for webpage/link documents.

article_cleaner.clean_article_text() has always replaced inline
![alt](url) markdown images with [imgN] markers (persisting the URL to
document_images), but that only happens at import/re-analysis time. Some
webpage/link documents never went through it (older imports, or a path
that bypassed it) and still carry raw image markdown — including base64
data: URIs — straight in text_md. That text feeds chunk analysis (when no
"reclean" happens), the whole-document embedding fallback, and NER
extraction, none of which benefit from an inline image.

Deliberately scoped to document_type IN ('webpage', 'link') only — NOT
obsidian_note (images there matter, see CLAUDE.md Epic 42) and NOT email
(article cleanup is never applied to emails, see
document_analysis_service.py). Uses article_cleaner.extract_inline_images()
— the same regex/skip-pattern logic clean_article_text() uses internally —
rather than the full cleanup pipeline, so this only ever touches images,
never footers/links/portal-specific rules.

Usage:
    cd backend
    .venv/Scripts/python imports/strip_webpage_images_backfill.py                # dry-run (default)
    .venv/Scripts/python imports/strip_webpage_images_backfill.py --apply
    .venv/Scripts/python imports/strip_webpage_images_backfill.py --id 10482
    .venv/Scripts/python imports/strip_webpage_images_backfill.py --apply --limit 20 --delay 0.5
    .venv/Scripts/python imports/strip_webpage_images_backfill.py --only-base64 --apply  # the worst offenders first
"""

import argparse
import logging
import time

from library.config_loader import load_config

cfg = load_config()  # noqa: F841 — side effect: populates os.environ for library modules

from library.article_cleaner import extract_inline_images  # noqa: E402
from library.db.engine import get_session  # noqa: E402
from library.db.models import Document  # noqa: E402
from library.document_images import replace_document_images  # noqa: E402

logger = logging.getLogger(__name__)

ELIGIBLE_TYPES = ("webpage", "link")


def find_candidates(session, *, only_base64: bool, doc_id: int | None):
    """Documents of an eligible type whose text_md still has raw !()[] images.

    The SQL LIKE is a cheap prefilter (index-free but avoids pulling every
    row's text_md into Python); extract_inline_images() is the real check.
    """
    query = session.query(Document).filter(
        Document.document_type.in_(ELIGIBLE_TYPES),
        Document.text_md.ilike("%![%](%"),
    )
    if only_base64:
        query = query.filter(Document.text_md.ilike("%data:image%"))
    if doc_id is not None:
        query = query.filter(Document.id == doc_id)
    return query.order_by(Document.id).all()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Write changes to the database (default: dry-run)")
    parser.add_argument("--id", type=int, help="Process a single document by id")
    parser.add_argument("--limit", type=int, help="Max number of documents to process")
    parser.add_argument("--only-base64", action="store_true", help="Only documents with a data:image URI in text_md")
    parser.add_argument("--delay", type=float, default=0.2, help="Seconds to sleep after each commit (default: 0.2)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s: %(message)s")

    session = get_session()
    try:
        docs = find_candidates(session, only_base64=args.only_base64, doc_id=args.id)
        if args.id is not None and not docs:
            single = Document.get_by_id(session, args.id)
            if single is not None and single.document_type not in ELIGIBLE_TYPES:
                logging.error(
                    "doc #%s has document_type=%r, not in %s — refusing (obsidian_note/email images are kept)",
                    args.id, single.document_type, ELIGIBLE_TYPES,
                )
                return
        if args.limit:
            docs = docs[: args.limit]

        logging.info("Found %d candidate document(s) (types=%s, only_base64=%s)", len(docs), ELIGIBLE_TYPES, args.only_base64)

        changed = 0
        total_images = 0
        for doc in docs:
            before_len = len(doc.text_md or "")
            new_text, images = extract_inline_images(doc.text_md or "")
            if not images:
                continue  # coarse LIKE prefilter false positive (e.g. lone "![" with no matching image)

            changed += 1
            total_images += len(images)
            logging.info(
                "doc #%s (%s): %d image(s) stripped, %s -> %s chars",
                doc.id, doc.document_type, len(images), f"{before_len:,}", f"{len(new_text):,}",
            )
            if args.verbose:
                for img in images:
                    logging.debug("  - %s", img["url"][:120])

            if args.apply:
                replace_document_images(session, doc.id, images)
                doc.text_md = new_text
                session.commit()
                if args.delay:
                    time.sleep(args.delay)

        if args.apply:
            logging.info("Done. Updated %d of %d documents (%d images moved to document_images).", changed, len(docs), total_images)
        else:
            logging.info(
                "Dry-run: %d of %d documents would change (%d images total). Re-run with --apply to save.",
                changed, len(docs), total_images,
            )
    finally:
        session.close()


if __name__ == "__main__":
    main()
