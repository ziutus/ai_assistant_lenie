#!/usr/bin/env python3
"""Fill ``persons.wikipedia_url`` from the Wikidata sitelinks of ``persons.wikidata_qid``.

Only persons that have a Wikidata id and no Wikipedia address yet are touched (a hand-entered address is never
overwritten). Polish Wikipedia is preferred, English is the fallback; a person with no article stays empty.
Wikidata is asked for 50 ids per request and the script pauses between batches, so run it in small portions
(``--limit``) rather than all at once.

Usage:
    cd backend
    .venv/Scripts/python imports/backfill_person_wikipedia_url.py                # dry-run (default)
    .venv/Scripts/python imports/backfill_person_wikipedia_url.py --apply --limit 200
"""

import argparse
import logging
import time

from library.config_loader import load_config

cfg = load_config()  # noqa: F841 — side effect: populates os.environ for library modules

from sqlalchemy import select  # noqa: E402

from library.db.engine import get_session  # noqa: E402
from library.db.models import Person  # noqa: E402
from library.wikidata_client import wikipedia_urls_for_qids  # noqa: E402

logger = logging.getLogger(__name__)

BATCH = 50
PAUSE_S = 1.0


def backfill(session, *, apply: bool, limit: int | None) -> tuple[int, int]:
    """Returns (persons checked, persons that got an address)."""
    query = select(Person).where(
        Person.wikidata_qid.is_not(None), Person.wikipedia_url.is_(None),
    ).order_by(Person.id)
    if limit:
        query = query.limit(limit)
    persons = list(session.execute(query).scalars())
    found = 0
    for start in range(0, len(persons), BATCH):
        batch = persons[start:start + BATCH]
        urls = wikipedia_urls_for_qids([p.wikidata_qid for p in batch])
        for person in batch:
            url = urls.get(person.wikidata_qid)
            if not url:
                continue
            found += 1
            print(f"#{person.id} {person.canonical_name} ({person.wikidata_qid}) -> {url}")
            if apply:
                person.wikipedia_url = url
        if apply:
            session.commit()
        time.sleep(PAUSE_S)
    return len(persons), found


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="write the addresses (default: dry-run)")
    parser.add_argument("--limit", type=int, default=None, help="check at most N persons")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    session = get_session()
    try:
        checked, found = backfill(session, apply=args.apply, limit=args.limit)
    finally:
        session.close()
    mode = "zapisano" if args.apply else "dry-run, nic nie zapisano"
    print(f"Sprawdzono osób: {checked}, z artykułem w Wikipedii: {found} ({mode})")


if __name__ == "__main__":
    main()
