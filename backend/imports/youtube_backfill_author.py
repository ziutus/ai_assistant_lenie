#!/usr/bin/env python3
"""One-off backfill: fetch the YouTube channel name (author) for existing videos missing it.

`author` is populated automatically for new videos since youtube_processing.py started
setting it (library/youtube_processing.py:130), but videos added before that change have
NULL author. This script re-fetches metadata for those videos via yt-dlp.

Usage:
    python imports/youtube_backfill_author.py --dry-run
    python imports/youtube_backfill_author.py
    python imports/youtube_backfill_author.py --limit 20 --delay 2
    python imports/youtube_backfill_author.py --no-proxy
"""

import argparse
import logging
import time

from library.config_loader import load_config

cfg = load_config()  # noqa: F841 — side effect: populates os.environ for library modules

from library.db.engine import get_session  # noqa: E402
from library.db.models import Document  # noqa: E402
from yt_dlp import YoutubeDL  # noqa: E402

logger = logging.getLogger(__name__)


def build_proxy(webshare_api_key: str) -> str | None:
    """Build a proxy URL string from Webshare credentials, or None if unavailable."""
    from youtube_transcript_api.proxies import WebshareProxyConfig

    from library.webshare_ip_auth import ensure_ip_authorized, get_proxy_credentials

    try:
        ensure_ip_authorized(webshare_api_key)
    except Exception as e:
        logger.warning(f"Webshare IP auth failed: {e} — proceeding without proxy")
        return None

    creds = get_proxy_credentials(webshare_api_key)
    if not creds:
        logger.warning("Webshare credentials unavailable — proceeding without proxy")
        return None

    return WebshareProxyConfig(proxy_username=creds[0], proxy_password=creds[1]).url


def fetch_author(url: str, proxy: str | None) -> str | None:
    """Fetch the channel name for a single YouTube video. Returns None on failure."""
    ydl_opts = {"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True}
    if proxy:
        ydl_opts["proxy"] = proxy
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return info.get("uploader")


def main():
    parser = argparse.ArgumentParser(
        description="Backfill the 'byline' (YouTube channel name) field for existing videos missing it."
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no DB writes")
    parser.add_argument("--limit", type=int, help="Max number of videos to process")
    parser.add_argument("--delay", type=float, default=1.5, help="Seconds to sleep between requests (default: 1.5)")
    parser.add_argument("--no-proxy", action="store_true", help="Disable Webshare proxy")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    webshare_api_key = cfg.get("WEBSHARE_API_KEY")
    proxy = None
    if args.no_proxy:
        logging.info("--no-proxy flag set — Webshare proxy disabled")
    elif webshare_api_key:
        proxy = build_proxy(webshare_api_key)
        if proxy:
            logging.info("Using Webshare rotating residential proxy")
    else:
        logging.info("No WEBSHARE_API_KEY configured — proceeding without proxy")

    session = get_session()
    try:
        query = session.query(Document).filter(
            Document.document_type == "youtube",
            Document.byline.is_(None),
        ).order_by(Document.id)
        if args.limit:
            query = query.limit(args.limit)
        docs = query.all()

        logging.info(f"Found {len(docs)} YouTube documents missing 'byline'")

        updated, failed = 0, 0
        for i, doc in enumerate(docs, start=1):
            logging.info(f"[{i}/{len(docs)}] doc #{doc.id}: {doc.url}")
            try:
                author = fetch_author(doc.url, proxy)
            except Exception as e:
                logging.warning(f"  FAILED: {e}")
                failed += 1
                time.sleep(args.delay)
                continue

            logging.info(f"  author: {author}")
            if not args.dry_run:
                doc.byline = author
                session.commit()
            updated += 1
            time.sleep(args.delay)

        logging.info(f"Done. Updated: {updated}, failed: {failed}, total: {len(docs)}")
        if args.dry_run:
            logging.info("(dry-run — no changes were saved)")
    finally:
        session.close()


if __name__ == "__main__":
    main()
