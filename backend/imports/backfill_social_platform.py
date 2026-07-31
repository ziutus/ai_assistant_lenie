#!/usr/bin/env python3
"""One-off backfill: social_platform for social_media_post documents added
before the LinkedIn-support commit (b0a1def8, 2026-07-28).

`documents.social_platform` and the extension logic that sends it
(`socialPlatformForUrl()` in web_chrome_extension/popup.js) were both
introduced in that commit. Documents of type social_media_post created
before it (via manual type selection in an older extension build) have
social_platform=NULL even though the platform is unambiguous from the URL
host (facebook.com / linkedin.com).

Usage:
    cd backend
    .venv/Scripts/python imports/backfill_social_platform.py            # dry-run (default)
    .venv/Scripts/python imports/backfill_social_platform.py --apply
    .venv/Scripts/python imports/backfill_social_platform.py --id 9347  # single document
"""

import argparse
import logging
from urllib.parse import urlparse

from library.config_loader import load_config

cfg = load_config()  # noqa: F841 — side effect: populates os.environ for library modules

from library.db.engine import get_session  # noqa: E402
from library.db.models import Document  # noqa: E402

logger = logging.getLogger(__name__)


def platform_for_url(url: str) -> str | None:
    """Mirror web_chrome_extension/popup.js's socialPlatformForUrl()."""
    try:
        hostname = urlparse(url).hostname or ""
    except ValueError:
        return None
    hostname = hostname.lower()
    if hostname == "facebook.com" or hostname.endswith(".facebook.com"):
        return "facebook"
    if hostname == "linkedin.com" or hostname.endswith(".linkedin.com"):
        return "linkedin"
    return None


def find_candidates(session, doc_id: int | None = None) -> list[Document]:
    query = session.query(Document).filter(
        Document.document_type == "social_media_post",
        Document.social_platform.is_(None),
    )
    if doc_id:
        query = query.filter(Document.id == doc_id)
    return query.order_by(Document.id).all()


def main():
    parser = argparse.ArgumentParser(
        description="Backfill social_platform for social_media_post documents from their URL host.",
    )
    parser.add_argument("--apply", action="store_true", help="Write changes to the database (default: dry-run)")
    parser.add_argument("--id", type=int, help="Process a single document by id")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    session = get_session()
    try:
        candidates = find_candidates(session, args.id)
        logging.info("Found %d social_media_post document(s) with social_platform=NULL", len(candidates))

        updated = 0
        for doc in candidates:
            platform = platform_for_url(doc.url)
            if not platform:
                logging.warning("doc #%s: could not determine platform from URL %s", doc.id, doc.url)
                continue
            updated += 1
            logging.info("doc #%s: social_platform -> %s (%s)", doc.id, platform, doc.url)
            if args.apply:
                doc.social_platform = platform
            else:
                session.expunge(doc)  # dry-run: don't let a later commit persist this

        if args.apply:
            session.commit()
            logging.info("Done. Updated %d of %d candidate documents.", updated, len(candidates))
        else:
            logging.info(
                "Dry-run: %d of %d candidate documents would be updated. Re-run with --apply to save.",
                updated, len(candidates),
            )
    finally:
        session.close()


if __name__ == "__main__":
    main()
