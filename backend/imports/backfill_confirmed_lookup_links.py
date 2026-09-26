#!/usr/bin/env python3
"""Backfill: promote already-confirmed OSINT lookup results into `contact_links`.

Usage (from backend, PYTHONPATH=. plus POSTGRESQL_* / SECRETS_BACKEND=env):
    python -m imports.backfill_confirmed_lookup_links            # dry-run (default)
    python -m imports.backfill_confirmed_lookup_links --apply
    python -m imports.backfill_confirmed_lookup_links --apply --contact-id 396

Idempotent: a URL already present in the contact's links (same type) is skipped, so
re-running adds nothing. One commit per contact. The history entry carries the original
confirmation date (`searched_at` of the lookup row).
"""

import argparse
import logging

from sqlalchemy import select

from library.contact_link_promotion import link_type_for_lookup, promote_lookup_result

logger = logging.getLogger(__name__)


def backfill(session, *, apply=False, contact_id=None):
    from library.db.models import Contact, ContactLookupResult

    query = select(ContactLookupResult).where(
        ContactLookupResult.status == "confirmed", ContactLookupResult.url.is_not(None),
    ).order_by(ContactLookupResult.contact_id, ContactLookupResult.id)
    if contact_id is not None:
        query = query.where(ContactLookupResult.contact_id == contact_id)

    promoted = skipped = 0
    for row in list(session.scalars(query)):
        if link_type_for_lookup(row.lookup_type, row.url) is None:
            skipped += 1
            continue
        contact = session.get(Contact, row.contact_id)
        if contact is None:
            skipped += 1
            continue
        try:
            added = promote_lookup_result(session, contact, row, confirmed_at=row.searched_at)
            if added is None:
                skipped += 1
                session.rollback()
                continue
            logger.info("%s contact=%s lookup=%s %s", "add" if apply else "would add", contact.id, row.id, row.url)
            promoted += 1
            if apply:
                session.commit()
            else:
                session.rollback()
        except Exception:
            session.rollback()
            logger.exception("failed contact=%s lookup=%s", row.contact_id, row.id)
    return promoted, skipped


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    parser.add_argument("--contact-id", type=int)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    from library.db.engine import get_session

    session = get_session()
    try:
        promoted, skipped = backfill(session, apply=args.apply, contact_id=args.contact_id)
    finally:
        session.close()
    print(f"{'applied' if args.apply else 'dry-run'}: {promoted} links to add, {skipped} skipped")


if __name__ == "__main__":
    main()
