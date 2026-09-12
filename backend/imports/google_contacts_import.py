#!/usr/bin/env python3
"""One-off import: load a Google Contacts CSV export into the private
contact book (library/db/models.py Contact — independent of the NER persons
registry), matching against existing contacts by name so people already in
the database (e.g. the 47 "Tuwima Gardens" creditors created by
court_case_contacts_import.py) don't get duplicated.

Two Google-Contacts-specific data-quality quirks are cleaned up on import:

1. Many rows have a hand-appended suffix like " - Tuwima Gardens" or
   " - Filip gr 4" on the Last Name field (a workaround for Google Contacts
   not having a real group for most of these people) instead of using the
   Labels column. The suffix (--suffix-text / --suffix-group, default
   "Tuwima Gardens" / "Tuwima Gardens Mieszkańcy") is stripped from
   first/last name and the contact is put in the suffix group instead —
   same group as any row that DOES carry the real group name in its Labels
   entry, so both paths land in one group. Stripping the suffix can leave
   last_name empty (a person whose surname isn't known) — in that case
   first_name is promoted to last_name (Contact.last_name is NOT NULL); if
   both are empty, the raw (unstripped) text is kept as last_name rather
   than losing the row.

2. The Labels column is Google's own multi-value group mechanism
   (`group1 ::: group2 ::: ...`). Google's own bookkeeping labels
   ('* myContacts', '* starred') are noise present on most rows and are
   dropped; every other label becomes (or reuses) a contact_groups row —
   this is the general-purpose group mechanism, not something built only
   for one particular group.

A contact matched by name only has empty fields filled in (email, phone,
address, company, position, birthday) and groups added — existing data is
never overwritten, mirroring court_case_contacts_import.py's approach.

Usage:
    cd backend
    python imports/google_contacts_import.py --csv "../tmp/contacts.csv"           # dry-run
    python imports/google_contacts_import.py --csv "../tmp/contacts.csv" --apply
    python imports/google_contacts_import.py --csv "../tmp/contacts_filip.csv" \\
        --suffix-text "Filip gr 4" --suffix-group "Przedszkole - Filip gr. 4" --apply
"""

import argparse
import csv
import datetime
import logging
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger("google_contacts_import")

DEFAULT_SUFFIX_TEXT = "Tuwima Gardens"
DEFAULT_SUFFIX_GROUP = "Tuwima Gardens Mieszkańcy"

# Google's own bookkeeping labels, not a group a person would recognize.
NOISE_LABELS = {"mycontacts", "starred"}


def _first_nonempty(row: dict, *keys: str) -> str | None:
    for key in keys:
        value = (row.get(key) or "").strip()
        if value:
            return value
    return None


def _parse_phone(row: dict) -> str | None:
    """contacts.phone_number is VARCHAR(30); a handful of rows have Google
    exporting the same (or a second) number joined with ' ::: ' into one
    field — take the first one rather than let a long combined value blow
    the column limit."""
    value = _first_nonempty(row, "Phone 1 - Value", "Phone 2 - Value")
    if value and ":::" in value:
        value = value.split(":::")[0].strip()
    return value[:30] if value else None


def _parse_birthday(value: str | None) -> datetime.date | None:
    if not value:
        return None
    value = value.strip()
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        return None  # Google exports "--MM-DD" for a year-less birthday; not representable here.


def _labels_to_groups(labels_raw: str) -> list[str]:
    groups = []
    for part in labels_raw.split(":::"):
        label = part.strip()
        if label.startswith("* "):
            label = label[2:].strip()
        if not label or label.lower() in NOISE_LABELS:
            continue
        groups.append(label)
    return groups


def _clean_name(first_raw: str, last_raw: str, suffix_re: re.Pattern) -> tuple[str | None, str, bool]:
    """Returns (first_name, last_name, has_suffix) with the hand-appended
    group suffix stripped and last_name guaranteed non-empty."""
    first = suffix_re.sub("", first_raw).strip()
    last = suffix_re.sub("", last_raw).strip()
    has_suffix = (first != first_raw.strip()) or (last != last_raw.strip())

    if last:
        return (first or None), last, has_suffix
    if first:
        return None, first, has_suffix  # last name unknown — promote first name so last_name stays non-null
    # Both empty after stripping (name was JUST the suffix) — keep raw text rather than lose the row.
    return None, (last_raw.strip() or first_raw.strip()), has_suffix


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--csv", required=True, help="Eksport CSV Kontaktów Google")
    parser.add_argument("--suffix-text", default=DEFAULT_SUFFIX_TEXT,
                         help=f"Tekst dopisany po ' - ' w nazwisku, oznaczający przynależność do grupy "
                              f"(domyślnie: {DEFAULT_SUFFIX_TEXT!r})")
    parser.add_argument("--suffix-group", default=DEFAULT_SUFFIX_GROUP,
                         help=f"Nazwa grupy kontaktów, do której trafiają wiersze z sufiksem "
                              f"(domyślnie: {DEFAULT_SUFFIX_GROUP!r})")
    parser.add_argument("--apply", action="store_true", help="Zapisz zmiany (domyślnie: tylko podgląd)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")

    # Not anchored to end-of-string: a row like "- Filip gr 4 mama Hugo" has extra
    # text (a hint worth keeping, e.g. the child's name) after the suffix — strip
    # just the suffix itself and keep whatever surrounds it rather than requiring
    # an exact trailing match and silently losing that context.
    suffix_re = re.compile(r"\s*-\s*" + re.escape(args.suffix_text) + r"\s*", re.IGNORECASE)
    suffix_group_name = args.suffix_group

    from sqlalchemy import select

    from imports.whatsapp_neighbor_profiles import normalize_name
    from library.contact_change_log import record_contact_change
    from library.db.engine import get_session
    from library.db.models import Contact, ContactCategory, ContactGroup

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

    group_by_name: dict[str, ContactGroup] = {
        g.name.lower(): g for g in session.scalars(select(ContactGroup))
    }

    def get_or_create_group(name: str) -> ContactGroup:
        group = group_by_name.get(name.lower())
        if group is None:
            group = ContactGroup(name=name)
            session.add(group)
            session.flush()
            group_by_name[name.lower()] = group
            logger.info("NOWA GRUPA: %s", name)
        return group

    matched_n, created_n, skipped_birthday_n = 0, 0, 0
    seen_keys: dict[str, int] = {}

    with open(args.csv, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            first_name, last_name, has_suffix = _clean_name(
                row.get("First Name") or "", row.get("Last Name") or "", suffix_re,
            )

            group_names = _labels_to_groups(row.get("Labels") or "")
            if has_suffix and suffix_group_name not in group_names:
                group_names.append(suffix_group_name)

            email = _first_nonempty(row, "E-mail 1 - Value", "E-mail 2 - Value", "E-mail 3 - Value")
            phone = _parse_phone(row)
            company = (row.get("Organization Name") or "").strip() or None
            position = (row.get("Organization Title") or "").strip() or None
            address = (row.get("Address 1 - Formatted") or "").strip() or None
            notes = (row.get("Notes") or "").strip() or None
            birthday = _parse_birthday(row.get("Birthday"))
            if (row.get("Birthday") or "").strip() and birthday is None:
                skipped_birthday_n += 1

            key = " ".join(sorted(normalize_name(f"{first_name or ''} {last_name}")))
            if key:
                seen_keys[key] = seen_keys.get(key, 0) + 1
                if seen_keys[key] > 1:
                    logger.warning("Zduplikowany wpis w CSV (ta sama osoba wystąpiła %d razy): %s %s",
                                    seen_keys[key], first_name, last_name)

            existing = existing_by_key.get(key)

            if existing:
                matched_n += 1
                new_groups = [g for g in group_names if g.lower() not in {eg.name.lower() for eg in existing.groups}]
                logger.info("DOPASOWANO #%d %s %s <- %s %s%s", existing.id, existing.first_name, existing.last_name,
                             first_name, last_name, f" (+grupy: {', '.join(new_groups)})" if new_groups else "")
                if args.apply:
                    changed_fields = []
                    if email and not existing.email:
                        existing.email = email
                        changed_fields.append("email")
                    if phone and not existing.phone_number:
                        existing.phone_number = phone
                        changed_fields.append("phone_number")
                    if company and not existing.company:
                        existing.company = company
                        changed_fields.append("company")
                    if position and not existing.position:
                        existing.position = position
                        changed_fields.append("position")
                    if address and not existing.address:
                        existing.address = address
                        changed_fields.append("address")
                    if birthday and not existing.birthday:
                        existing.birthday = birthday
                        changed_fields.append("birthday")
                    if notes and (not existing.notes or notes not in existing.notes):
                        existing.notes = f"{existing.notes}\n{notes}" if existing.notes else notes
                        changed_fields.append("notes")
                    for group_name in group_names:
                        group = get_or_create_group(group_name)
                        if group not in existing.groups:
                            existing.groups.append(group)
                    record_contact_change(
                        session, existing, "google_import", changed_fields=changed_fields,
                        note=f"Uzupełniono puste pola z eksportu Kontaktów Google ({args.csv})" if changed_fields else None,
                    )
            else:
                created_n += 1
                logger.info("NOWY KONTAKT: %s %s%s", first_name or "", last_name,
                             f" (grupy: {', '.join(group_names)})" if group_names else "")
                if args.apply:
                    contact = Contact(
                        category_id=default_category.id,
                        first_name=first_name,
                        last_name=last_name,
                        phone_number=phone,
                        email=email,
                        company=company,
                        position=position,
                        address=address,
                        birthday=birthday,
                        notes=notes,
                    )
                    for group_name in group_names:
                        contact.groups.append(get_or_create_group(group_name))
                    session.add(contact)
                    session.flush()
                    record_contact_change(
                        session, contact, "google_import",
                        changed_fields=["first_name", "last_name", "category_id"],
                        note=f"Zaimportowano z eksportu Kontaktów Google ({args.csv})",
                    )
                    # Deliberately NOT added to existing_by_key: two different people can
                    # share a weak key (e.g. no last name — "Agnieszka" x3), and matching a
                    # later CSV row against a contact created earlier in this same run would
                    # silently merge two distinct neighbors instead of creating both. A CSV
                    # row that really is a duplicate re-entry of the same person just creates
                    # a second Contact row here, safe to merge manually afterwards.

        if args.apply:
            session.commit()

    session.close()

    print()
    print(f"Wierszy: dopasowanych do istniejących kontaktów: {matched_n}, nowych: {created_n}")
    if skipped_birthday_n:
        print(f"Pominięte urodziny bez roku (Google '--MM-DD'): {skipped_birthday_n}")
    if not args.apply:
        print("\n(dry-run — użyj --apply, żeby zapisać zmiany)")


if __name__ == "__main__":
    main()
