#!/usr/bin/env python3
"""Backfill missing contact photo thumbnails, sequentially with one commit per contact.

Usage (from backend):
    uv run python -m imports.contact_photo_thumbnails_backfill --dry-run
    uv run python -m imports.contact_photo_thumbnails_backfill --apply --limit 100
    uv run python -m imports.contact_photo_thumbnails_backfill --apply --id 123

Dry-run is the default: reads and decodes originals but writes no blobs or rows.
Re-running skips contacts that already have a thumbnail.
"""

import argparse
import logging

from sqlalchemy import or_

from library.contact_photo_thumbnails import _photo_thumbnail_storage_key, generate_photo_thumbnail

logger = logging.getLogger(__name__)


def backfill(session, storage, *, apply=False, contact_id=None, limit=None):
    from library.db.models import Contact

    query = session.query(Contact.id).filter(
        Contact.photo_storage_key.is_not(None),
        Contact.photo_storage_key != "",
        or_(Contact.photo_thumbnail_storage_key.is_(None), Contact.photo_thumbnail_storage_key == ""),
    )
    if contact_id is not None:
        query = query.filter(Contact.id == contact_id)
    query = query.order_by(Contact.id)
    if limit is not None:
        query = query.limit(limit)
    ids = [row[0] for row in query.all()]
    processed = errored = 0
    for id_ in ids:
        try:
            contact = session.get(Contact, id_)
            if contact is None or not contact.photo_storage_key or contact.photo_thumbnail_storage_key:
                continue
            thumbnail = generate_photo_thumbnail(storage.get_bytes(contact.photo_storage_key))
            if apply:
                key = _photo_thumbnail_storage_key(contact.uuid)
                storage.put_bytes(key, thumbnail, content_type="image/jpeg")
                contact.photo_thumbnail_storage_key = key
                session.commit()
            processed += 1
            logger.info("Contact #%s: %s", id_, "updated" if apply else "would update")
        except Exception:
            session.rollback()
            errored += 1
            logger.exception("Contact #%s: thumbnail backfill failed", id_)
    logger.info("%s: processed=%d errored=%d", "Done" if apply else "Dry-run", processed, errored)
    return processed, errored


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="Save thumbnails and database keys")
    mode.add_argument("--dry-run", action="store_true", help="Preview only (default)")
    parser.add_argument("--id", type=int, help="Process one contact")
    parser.add_argument("--limit", type=int, help="Maximum number of contacts")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    from library.config_loader import load_config

    cfg = load_config()
    from library.db.engine import get_session
    from library.storage import storage_from_config

    session = get_session()
    try:
        _, errored = backfill(session, storage_from_config(cfg), apply=args.apply,
                              contact_id=args.id, limit=args.limit)
        return 1 if errored else 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
