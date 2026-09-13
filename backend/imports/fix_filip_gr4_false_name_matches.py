#!/usr/bin/env python3
"""One-off correction: google_contacts_import.py's first-name-only weak-key
matching (see feedback_no_merge_unverifiable_contacts.md) matched 4 rows in
tmp/contacts_filip.csv against pre-existing contacts from an *earlier*,
unrelated import (the 2026-08-24 "Tuwima Gardens" / "meski_krag_lodz" full
Google Contacts import) purely because both share a bare first name with no
surname on file. Phone numbers for all 4 pairs differ, which is strong
evidence they are different people:

    id=114 "Aneta"     existing +48507012684  vs CSV +48663207619
    id=178 "Edyta"      existing +48667662886  vs CSV +48690117135
    id=291 "Magdalena"  existing +48605422697  vs CSV +48514745059
    id=443 "Tomasz"     existing +48 796 234 921 vs CSV +48504133786

This removes the wrongly-added "Przedszkole - Filip gr. 4" membership from
those 4 existing contacts and creates 4 new Contact rows (one per name)
carrying the CSV's own phone number and the correct group, so the group
ends up representing 4 distinct people instead of 4 wrong ones.

Usage:
    cd backend
    python imports/fix_filip_gr4_false_name_matches.py            # dry-run
    python imports/fix_filip_gr4_false_name_matches.py --apply
"""

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger("fix_filip_gr4_false_name_matches")

GROUP_NAME = "Przedszkole - Filip gr. 4"

# (existing contact id wrongly tagged, bare name, correct phone from tmp/contacts_filip.csv)
CORRECTIONS = [
    (114, "Aneta", "+48663207619"),
    (178, "Edyta", "+48690117135"),
    (291, "Magdalena", "+48514745059"),
    (443, "Tomasz", "+48504133786"),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Zapisz zmiany (domyślnie: tylko podgląd)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    from sqlalchemy import select

    from library.contact_change_log import record_contact_change
    from library.db.engine import get_session
    from library.db.models import Contact, ContactCategory, ContactGroup

    session = get_session()

    default_category = session.execute(
        select(ContactCategory).where(ContactCategory.name == "Osoba prywatna")
    ).scalars().first()
    group = session.execute(select(ContactGroup).where(ContactGroup.name == GROUP_NAME)).scalars().first()
    if default_category is None or group is None:
        logger.error("Brak kategorii 'Osoba prywatna' lub grupy %r — przerywam", GROUP_NAME)
        session.close()
        return

    for contact_id, name, phone in CORRECTIONS:
        existing = session.get(Contact, contact_id)
        if existing is None:
            logger.warning("Kontakt #%d nie istnieje — pomijam", contact_id)
            continue
        if group not in existing.groups:
            logger.warning("Kontakt #%d (%s) nie jest już w grupie %r — pomijam usunięcie", contact_id, name, GROUP_NAME)
        else:
            logger.info("USUWAM błędną grupę u #%d %s %s (pozostałe grupy: %s)", existing.id, existing.first_name,
                         existing.last_name, [g.name for g in existing.groups if g != group])
            if args.apply:
                existing.groups.remove(group)
                record_contact_change(
                    session, existing, "google_import", changed_fields=["groups"],
                    note=(f"Cofnięto błędne dopasowanie po samym imieniu z importu 'Przedszkole - Filip gr. 4' "
                          f"(inny numer telefonu w CSV: {phone}) — patrz fix_filip_gr4_false_name_matches.py"),
                )

        logger.info("TWORZĘ nowy kontakt: %s, tel=%s, grupa=%s", name, phone, GROUP_NAME)
        if args.apply:
            new_contact = Contact(
                category_id=default_category.id,
                first_name=None,
                last_name=name,
                phone_number=phone,
            )
            new_contact.groups.append(group)
            session.add(new_contact)
            session.flush()
            record_contact_change(
                session, new_contact, "google_import",
                changed_fields=["first_name", "last_name", "phone_number", "category_id"],
                note=f"Utworzony po korekcie błędnego dopasowania kontaktu #{contact_id} — "
                     f"patrz fix_filip_gr4_false_name_matches.py",
            )

    if args.apply:
        session.commit()
        logger.info("Zapisano.")
    else:
        print("\n(dry-run — użyj --apply, żeby zapisać zmiany)")

    session.close()


if __name__ == "__main__":
    main()
