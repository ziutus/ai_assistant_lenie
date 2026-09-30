#!/usr/bin/env python3
"""One-off repair: re-label Facebook-derived contact facts that were stored as the owner's own input.

The Facebook enrichment skill used to save birthday / gender / current_city / hometown with a plain
``PATCH /contacts/<id>``. Since the sourced-fact layer landed, that endpoint records every value as a
``user_manual`` assertion and pins its slot — so a Facebook claim (including a vanity birth year) looks
like something the owner typed and can never be outranked by a better source.

This script finds ``user_manual`` assertions written by one API key (the key the skill ran with) since a
given moment and re-labels them to another source (default ``facebook``), releasing the manual pin. The
value stays selected and the Contact columns are not touched; only the provenance changes.

Use ``--asserted-by`` with the key that ran the skill and nothing else (``asserted_by`` is
``api-key:<id>`` for API-key callers, ``user:<id>`` for people using the web UI): manual edits made by a
person must never be re-labelled.

Usage:
    cd backend
    .venv/Scripts/python imports/reattribute_facebook_facts.py --asserted-by api-key:63 --since 2026-09-28T14:45:00
    .venv/Scripts/python imports/reattribute_facebook_facts.py --asserted-by api-key:63 --since 2026-09-28T14:45:00 --apply
    .venv/Scripts/python imports/reattribute_facebook_facts.py ... --contact 586      # single contact
"""

import argparse
import datetime as dt
import logging
from collections import Counter

from library.config_loader import load_config

cfg = load_config()  # noqa: F841 — side effect: populates os.environ for library modules

from sqlalchemy import select  # noqa: E402

from library import contact_facts_service  # noqa: E402
from library.db.engine import get_session  # noqa: E402
from library.db.models import ContactFactAssertion, ContactFactSlot  # noqa: E402

logger = logging.getLogger(__name__)


def candidate_assertions(session, asserted_by: str, since: dt.datetime, contact_id: int | None = None):
    """Rows (assertion, slot) that look like skill-written values filed under ``user_manual``."""
    query = (
        select(ContactFactAssertion, ContactFactSlot)
        .join(ContactFactSlot, ContactFactSlot.id == ContactFactAssertion.slot_id)
        .where(
            ContactFactAssertion.source_key == "user_manual",
            ContactFactAssertion.asserted_by == asserted_by,
            ContactFactAssertion.created_at >= since,
            ContactFactSlot.attribute_key.in_(contact_facts_service.EXTERNAL_ASSERTION_ATTRIBUTES),
        )
        .order_by(ContactFactSlot.contact_id, ContactFactSlot.attribute_key, ContactFactAssertion.id)
    )
    if contact_id is not None:
        query = query.where(ContactFactSlot.contact_id == contact_id)
    return session.execute(query).all()


def main():
    parser = argparse.ArgumentParser(description="Re-label Facebook facts that were stored as user_manual.")
    parser.add_argument("--asserted-by", required=True, help="asserted_by value to repair, e.g. api-key:63")
    parser.add_argument("--since", required=True, type=dt.datetime.fromisoformat,
                        help="Only assertions created at or after this ISO timestamp (server time, UTC)")
    parser.add_argument("--source", default="facebook", help="Source to re-label to (default: facebook)")
    parser.add_argument("--contact", type=int, help="Process a single contact by id")
    parser.add_argument("--apply", action="store_true", help="Write changes to the database (default: dry-run)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    session = get_session()
    try:
        rows = candidate_assertions(session, args.asserted_by, args.since, args.contact)
        by_attribute = Counter(slot.attribute_key for _, slot in rows)
        contacts = {slot.contact_id for _, slot in rows}
        logger.info("%d assertion(s) in %d contact(s) match: %s", len(rows), len(contacts), dict(by_attribute))
        changed = skipped = 0
        for assertion, slot in rows:
            try:
                contact_facts_service.reassign_assertion_source(session, assertion.id, args.source)
            except ValueError as exc:
                skipped += 1
                logger.warning("contact %s %s (assertion %s) skipped: %s",
                               slot.contact_id, slot.attribute_key, assertion.id, exc)
                continue
            changed += 1
            logger.debug("contact %s %s: assertion %s -> %s", slot.contact_id, slot.attribute_key,
                         assertion.id, args.source)
        if args.apply:
            session.commit()
            logger.info("APPLIED: %d re-labelled, %d skipped.", changed, skipped)
        else:
            session.rollback()
            logger.info("Dry-run: %d would be re-labelled, %d skipped. Re-run with --apply to write.",
                        changed, skipped)
    finally:
        session.close()


if __name__ == "__main__":
    main()
