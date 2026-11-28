"""Propose Wikidata relations for existing persons; dry-run unless --apply."""

import argparse
import json

from sqlalchemy import func, select

from library.db.models import DocumentPerson, Person
from library.wikidata_relations import propose_for_person


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--person-id", type=int)
    parser.add_argument("--delay", type=float, default=1.0)
    args = parser.parse_args()
    if args.limit < 1 or args.delay < 0:
        parser.error("limit must be positive and delay nonnegative")
    from library.db.engine import get_session
    session = get_session()
    try:
        query = select(Person.id).outerjoin(DocumentPerson, DocumentPerson.person_id == Person.id).where(
            Person.wikidata_qid.is_not(None)).group_by(Person.id).order_by(func.count(DocumentPerson.id).desc(), Person.id)
        if args.person_id:
            query = query.where(Person.id == args.person_id)
        for identifier in session.scalars(query.limit(args.limit)).all():
            result = propose_for_person(session, identifier, apply=args.apply, delay=args.delay)
            if args.apply:
                session.commit()
            print(json.dumps(result, ensure_ascii=False))
    finally:
        session.rollback()
        session.close()


if __name__ == "__main__":
    main()
