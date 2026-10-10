#!/usr/bin/env python3
"""One-off backfill: remove Onet's "Czytaj nas częściej w Google" promo block
from already-stored `text_md`.

The block is the Onet logo image (`[imgN: Logo]`, cdn.wiadomosci.onet.pl/img/
Logo_desktop_Onet.svg) followed by the "Dodaj w Google [linkN]" button that
points at google.com/preferences/source?q=onet.pl. `library/article_cleaner.py`
now drops both at import time (logo via `_SKIP_IMAGE_URL_PATTERNS`, the button
because `_clean_lines_onet` strips the `[linkN]` marker before comparing); this
script cleans documents imported before that fix (doc 10752 and ~13 others).

Only `webpage`/`link` documents on onet.pl are touched. Documents that already
have embeddings or analysis runs are reported and skipped unless
`--include-analyzed` is passed (then only `text_md` and the logo
`document_images` row change; existing chunks/embeddings keep the old text).
Other `[imgN]`/`[linkN]` markers are left as they are — `document_images`
rows keep their stored positions, and links are not stored anywhere.

Usage:
    cd backend
    PYTHONPATH=. .venv/Scripts/python imports/strip_onet_google_promo_backfill.py            # dry-run (default)
    PYTHONPATH=. .venv/Scripts/python imports/strip_onet_google_promo_backfill.py --apply
    PYTHONPATH=. .venv/Scripts/python imports/strip_onet_google_promo_backfill.py --id 10752
"""

import argparse
import logging

from library.config_loader import load_config

cfg = load_config()  # noqa: F841 — side effect: populates os.environ for library modules

from sqlalchemy import func, select  # noqa: E402

from library.article_cleaner import strip_onet_google_promo  # noqa: E402
from library.db.engine import get_session  # noqa: E402
from library.db.models import Document, DocumentAnalysisRun, DocumentEmbedding, DocumentImage  # noqa: E402

logger = logging.getLogger(__name__)

_LOGO_URL_FRAGMENT = "Logo_desktop_Onet"


def _is_onet(url: str) -> bool:
    return "onet.pl" in url.split("/")[2] if "//" in url else False


def find_candidates(session, doc_id: int | None = None) -> list[Document]:
    query = session.query(Document).filter(
        Document.document_type.in_(("webpage", "link")),
        Document.url.ilike("%onet.pl%"),
        Document.text_md.like("%Dodaj w Google%"),
    )
    if doc_id:
        query = query.filter(Document.id == doc_id)
    return [doc for doc in query.order_by(Document.id).all() if _is_onet(doc.url)]


def _has_derived_data(session, doc_id: int) -> bool:
    embeddings = session.scalar(
        select(func.count()).select_from(DocumentEmbedding).where(DocumentEmbedding.document_id == doc_id),
    )
    runs = session.scalar(
        select(func.count()).select_from(DocumentAnalysisRun).where(DocumentAnalysisRun.document_id == doc_id),
    )
    return bool(embeddings) or bool(runs)


def main():
    parser = argparse.ArgumentParser(
        description="Remove Onet's 'Dodaj w Google' promo block from stored text_md.",
    )
    parser.add_argument("--apply", action="store_true", help="Write changes to the database (default: dry-run)")
    parser.add_argument("--id", type=int, help="Process a single document by id")
    parser.add_argument(
        "--include-analyzed", action="store_true",
        help="Also update documents that already have embeddings/analysis runs (chunks keep the old text)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    session = get_session()
    try:
        candidates = find_candidates(session, args.id)
        logging.info("Found %d candidate onet.pl document(s)", len(candidates))

        changed = skipped = 0
        for doc in candidates:
            new_text_md = strip_onet_google_promo(doc.text_md)
            if new_text_md == doc.text_md:
                logging.info("doc #%s: block not in the expected shape, nothing to strip", doc.id)
                continue
            if _has_derived_data(session, doc.id) and not args.include_analyzed:
                skipped += 1
                logging.warning("doc #%s: has embeddings/analysis runs, skipping (--include-analyzed)", doc.id)
                continue

            logos = session.query(DocumentImage).filter(
                DocumentImage.document_id == doc.id,
                DocumentImage.storage_key.is_(None),
                DocumentImage.url.ilike(f"%{_LOGO_URL_FRAGMENT}%"),
            ).all()
            changed += 1
            logging.info(
                "doc #%s: text_md -%d chars, %d logo image row(s)",
                doc.id, len(doc.text_md) - len(new_text_md), len(logos),
            )
            if args.apply:
                doc.text_md = new_text_md
                for logo in logos:
                    session.delete(logo)

        if args.apply:
            session.commit()
            logging.info("Done. Updated %d of %d candidates (%d skipped).", changed, len(candidates), skipped)
        else:
            session.rollback()
            logging.info(
                "Dry-run: %d of %d candidates would be updated (%d would be skipped). Re-run with --apply to save.",
                changed, len(candidates), skipped,
            )
    finally:
        session.close()


if __name__ == "__main__":
    main()
