#!/usr/bin/env python3
"""One-off backfill: every Contact created by court_case_contacts_import.py
(identified by the "Sprawa Tuwima Gardens (KRZ)" marker it writes into
Contact.notes) is, by definition, a Tuwima Gardens resident/creditor — but
only the subset that also matched a row in the Google Contacts CSV export
got put into the "Tuwima Gardens Mieszkańcy" contact_groups group by
google_contacts_import.py (26 of 47). This adds the remaining KRZ contacts
to that group so group membership reflects reality regardless of whether a
person happened to be in the CSV export.

Usage:
    cd backend
    python imports/backfill_krz_tuwima_group.py            # dry-run
    python imports/backfill_krz_tuwima_group.py --apply
"""

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger("backfill_krz_tuwima_group")

GROUP_NAME = "Tuwima Gardens Mieszkańcy"
NOTES_MARKER = "Tuwima Gardens (KRZ)"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Zapisz zmiany (domyślnie: tylko podgląd)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    from sqlalchemy import select

    from library.db.engine import get_session
    from library.db.models import Contact, ContactGroup

    session = get_session()

    group = session.execute(select(ContactGroup).where(ContactGroup.name == GROUP_NAME)).scalars().first()
    if group is None:
        logger.error("Grupa '%s' nie istnieje — przerywam", GROUP_NAME)
        session.close()
        return

    krz_contacts = session.execute(
        select(Contact).where(Contact.notes.ilike(f"%{NOTES_MARKER}%"))
    ).scalars().all()

    added_n = 0
    for contact in krz_contacts:
        if group not in contact.groups:
            added_n += 1
            logger.info("DODAJ DO GRUPY: #%d %s %s", contact.id, contact.first_name, contact.last_name)
            if args.apply:
                contact.groups.append(group)

    if args.apply:
        session.commit()
    session.close()

    print()
    print(f"Kontaktów KRZ (Tuwima Gardens): {len(krz_contacts)}, dodanych do grupy: {added_n}")
    if not args.apply:
        print("\n(dry-run — użyj --apply, żeby zapisać zmiany)")


if __name__ == "__main__":
    main()
