#!/usr/bin/env python3
"""One-off import: match a Krajowy Rejestr Zadluznikow (KRZ) court-case creditor
list ("Wierzyciel") for the Tuwima Gardens development against the existing
private contact book (library/db/models.py Contact — independent of the NER
persons registry), creating a new Contact for anyone not already present.

Stores each person's PESEL and the birth date it encodes (library/pesel.py) so
Contact.birthday can drive a future birthday-reminder feature. Records the KRZ
role and "Do Doreczen Konto" (court e-delivery account number) in Contact.notes
rather than a dedicated column — that account is only meaningful within this
one case, not a stable person attribute worth its own schema yet.

A creditor whose "Do Doreczen Konto" is 'Brak' has no KRZ e-delivery account
and needs to be told how to create one — the dry-run report lists them.

Matching an existing Contact is exact-name (first+last, diacritic/case
folded via imports.whatsapp_neighbor_profiles.normalize_name); a match only
writes pesel/birthday/notes onto the existing row — the two records are NOT
otherwise merged ("scalenie pozniej" per the user). Optionally backfills
phone_number for newly-created contacts from a Google Contacts CSV export
(--contacts-csv), by the same exact-name matching.

Usage:
    cd backend
    python imports/court_case_contacts_import.py --csv "../tmp/krz_wierzyciele_tuwima.csv"                 # dry-run
    python imports/court_case_contacts_import.py --csv "..." --contacts-csv "../tmp/contacts.csv" --apply
"""

import argparse
import csv
import logging
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger("court_case_contacts_import")


def load_phone_by_name(csv_path: str, suffix: str | None = None) -> dict[str, str]:
    """Reverse of whatsapp_neighbor_profiles.load_contacts: name -> phone, for
    backfilling a newly-created Contact's phone_number from the same Google
    Contacts export used to resolve WhatsApp phone-only senders."""
    from imports.whatsapp_neighbor_profiles import normalize_name

    suffix_re = re.compile(r"\s*-\s*" + re.escape(suffix) + r"\s*$", re.IGNORECASE) if suffix else None
    result: dict[str, str] = {}
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            parts = []
            for col in ("First Name", "Last Name"):
                token = (row.get(col) or "").strip()
                if suffix_re:
                    token = suffix_re.sub("", token).strip()
                if token:
                    parts.append(token)
            key = " ".join(sorted(normalize_name(" ".join(parts)))) if parts else ""
            if not key:
                continue
            phone = (row.get("Phone 1 - Value") or row.get("Phone 2 - Value") or "").strip()
            if phone and key not in result:
                result[key] = phone
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--csv", required=True,
                         help="CSV listy wierzycieli (kolumny: rola,konto_doreczen,imie,nazwisko,nazwa_firmy,miejsce,pesel,nip,krs)")
    parser.add_argument("--case-label", default="Tuwima Gardens (KRZ)", help="Etykieta sprawy dopisywana do notatki kontaktu")
    parser.add_argument("--contacts-csv", default=None, help="Opcjonalny eksport Kontaktów Google do uzupełnienia numeru telefonu nowych kontaktów")
    parser.add_argument("--contacts-suffix", default="Tuwima Gardens")
    parser.add_argument("--apply", action="store_true", help="Zapisz zmiany (domyślnie: tylko podgląd)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")

    from sqlalchemy import select

    from imports.whatsapp_neighbor_profiles import normalize_name
    from library.db.engine import get_session
    from library.db.models import Contact, ContactCategory, ContactOrganization
    from library.pesel import is_valid_pesel, pesel_birthdate

    phone_by_name = load_phone_by_name(args.contacts_csv, args.contacts_suffix) if args.contacts_csv else {}

    session = get_session()

    default_category = session.execute(
        select(ContactCategory).where(ContactCategory.name == "Osoba prywatna")
    ).scalars().first()
    if default_category is None:
        logger.error("Brak kategorii 'Osoba prywatna' w contact_categories — przerywam")
        session.close()
        return

    existing_by_key: dict[str, Contact] = {}
    for c in session.scalars(select(Contact)):
        key = " ".join(sorted(normalize_name(f"{c.first_name or ''} {c.last_name}")))
        if key:
            existing_by_key.setdefault(key, c)

    matched_n, created_n, invalid_pesel_n = 0, 0, 0
    no_account = []

    with open(args.csv, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            imie = row["imie"].strip()
            nazwisko = row["nazwisko"].strip()
            firma = (row.get("nazwa_firmy") or "").strip()
            miejsce = (row.get("miejsce") or "").strip()
            pesel = (row.get("pesel") or "").strip()
            nip = (row.get("nip") or "").strip()
            konto = (row.get("konto_doreczen") or "").strip()
            rola = (row.get("rola") or "").strip()

            if konto.lower() == "brak":
                no_account.append(f"{imie} {nazwisko}")

            if pesel and not is_valid_pesel(pesel):
                invalid_pesel_n += 1
                logger.warning("PESEL nie przechodzi walidacji sumy kontrolnej: %s %s (%s)", imie, nazwisko, pesel)

            birthdate = pesel_birthdate(pesel) if pesel else None
            key = " ".join(sorted(normalize_name(f"{imie} {nazwisko}")))
            existing = existing_by_key.get(key)
            note_line = (
                f"Sprawa {args.case_label}: {rola}, konto do doręczeń KRZ: "
                f"{konto or 'BRAK — wymaga założenia konta w systemie sądowym'}."
            )

            if existing:
                matched_n += 1
                logger.info("DOPASOWANO #%d %s %s <- %s %s", existing.id, existing.first_name, existing.last_name, imie, nazwisko)
                if args.apply:
                    if pesel and not existing.pesel:
                        existing.pesel = pesel
                    if birthdate and not existing.birthday:
                        existing.birthday = birthdate
                    existing.notes = (existing.notes + "\n" + note_line) if existing.notes else note_line
            else:
                created_n += 1
                phone = phone_by_name.get(key)
                logger.info("NOWY KONTAKT: %s %s%s", imie, nazwisko, f" (tel. {phone})" if phone else "")
                if args.apply:
                    contact = Contact(
                        category_id=default_category.id,
                        first_name=imie,
                        last_name=nazwisko,
                        phone_number=phone,
                        address=miejsce or None,
                        pesel=pesel or None,
                        birthday=birthdate,
                        notes=note_line,
                    )
                    session.add(contact)
                    session.flush()
                    if firma:
                        session.add(ContactOrganization(
                            contact_id=contact.id,
                            org_type="jdg",
                            organization_name=firma,
                            nip=nip or None,
                        ))

        if args.apply:
            session.commit()

    session.close()

    print()
    print(f"Wierszy: dopasowanych do istniejących kontaktów: {matched_n}, nowych: {created_n}")
    if invalid_pesel_n:
        print(f"UWAGA: PESEL z błędną sumą kontrolną: {invalid_pesel_n}")
    print(f"\nOsoby BEZ konta do doręczeń w KRZ (do powiadomienia, jak założyć konto): {len(no_account)}")
    for name in no_account:
        print(f"  - {name}")
    if not args.apply:
        print("\n(dry-run — użyj --apply, żeby zapisać zmiany)")


if __name__ == "__main__":
    main()
