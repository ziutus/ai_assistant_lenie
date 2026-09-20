#!/usr/bin/env python3
"""One-off import: load a Google Contacts CSV export into the private
contact book (library/db/models.py Contact — independent of the NER persons
registry), matching all normalized phone numbers, then unambiguous full names, so people already in
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

A matched contact gains new addresses and has empty company/position/birthday fields filled
and groups added. All phone numbers and emails are preserved, with missing
values appended to the ordered lists without replacing the existing primary.
Yearless birthdays populate month/day only. Ambiguous identity matches are
reported and skipped; birthday conflicts retain the existing date. Dry-run
uses detached snapshots and the same matching decisions as --apply.

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
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger("google_contacts_import")

DEFAULT_SUFFIX_TEXT = "Tuwima Gardens"
DEFAULT_SUFFIX_GROUP = "Tuwima Gardens Mieszkańcy"

# Google's own bookkeeping labels, not a group a person would recognize.
NOISE_LABELS = {"mycontacts", "starred"}


def _parse_channels(row: dict, prefix: str, field: str) -> list[dict]:
    from library.contact_channels import channel_key, normalize_channels

    result, seen = [], set()
    columns = sorted(
        (key for key in row if re.fullmatch(rf"{re.escape(prefix)} \d+ - Value", key)),
        key=lambda key: int(key.split(" ")[1]),
    )
    for key in columns:
        label = (row.get(key.replace(" - Value", " - Type")) or "").strip() or None
        for value in (row.get(key) or "").split(":::"):
            value = value.strip()
            normalized_key = channel_key(value, field)
            if value and normalized_key not in seen:
                seen.add(normalized_key)
                result.append({"value": value, "label": label})
    return normalize_channels(result, field)


def _parse_birthday(value: str | None) -> dict | None:
    """A missing/invalid date returns None; never invent a birth year."""
    value = (value or "").strip()
    if not value:
        return None
    try:
        if re.fullmatch(r"--\d{2}-\d{2}", value):
            date = datetime.date.fromisoformat("2000" + value[1:])
            return {"birthday_month": date.month, "birthday_day": date.day}
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return {"birthday": datetime.date.fromisoformat(value)}
    except ValueError:
        pass
    return None


def _birthday_patch(contact, parsed: dict | None) -> tuple[dict, bool]:
    """Fill unknown birthday data; report conflicts without overwriting it."""
    if not parsed:
        return {}, False
    full = parsed.get("birthday")
    incoming = (full.month, full.day) if full else (parsed["birthday_month"], parsed["birthday_day"])
    if contact.birthday:
        known = (contact.birthday.month, contact.birthday.day)
        return {}, (contact.birthday != full if full else known != incoming)
    month, day = contact.birthday_month, contact.birthday_day
    if (month is not None and month != incoming[0]) or (day is not None and day != incoming[1]):
        return {}, True
    if full:
        return {"birthday": full}, False
    return {field: value for field, value in parsed.items() if getattr(contact, field) is None}, False


def _name_key(contact) -> str | None:
    from imports.whatsapp_neighbor_profiles import normalize_name

    if not contact.first_name or not contact.last_name:
        return None
    return " ".join(sorted(normalize_name(f"{contact.first_name} {contact.last_name}"))) or None


class _ContactIndex:
    """All valid numbers participate; collisions are retained, never first-wins."""

    def __init__(self, contacts):
        self.phones, self.names, self.contact_phones = {}, {}, {}
        for contact in contacts:
            self.add(contact, include_name=True)

    def add(self, contact, extra_phones=(), *, include_name=False):
        from library.contact_channels import contact_channels
        from library.contact_phones import phone_identity_key

        keys = self.contact_phones.setdefault(id(contact), set())
        for entry in [*contact_channels(contact, "phone_numbers"), *extra_phones]:
            key = phone_identity_key(entry["value"])
            if key:
                keys.add(key)
                self.phones.setdefault(key, {})[id(contact)] = contact
        name = _name_key(contact) if include_name else None
        if name:
            self.names.setdefault(name, {})[id(contact)] = contact

    def match(self, phones: list[dict], name: str | None):
        from library.contact_phones import phone_identity_key

        keys = {key for entry in phones if (key := phone_identity_key(entry["value"]))}
        candidates = {cid: contact for key in keys for cid, contact in self.phones.get(key, {}).items()}
        named = self.names.get(name, {})
        if len(candidates) > 1:
            return None, "telefony wskazują kilka kontaktów"
        if candidates:
            cid, contact = next(iter(candidates.items()))
            if name and _name_key(contact) and name != _name_key(contact):
                return None, "ten sam telefon, ale różne nazwy — wymaga sprawdzenia"
            if named and cid not in named:
                return None, "telefon i nazwa wskazują różne kontakty"
            return contact, None
        if len(named) > 1:
            return None, "nazwa wskazuje kilka kontaktów"
        if named:
            cid, contact = next(iter(named.items()))
            if keys and self.contact_phones[cid] and keys.isdisjoint(self.contact_phones[cid]):
                return None, "ta sama nazwa, ale inne telefony — wymaga sprawdzenia"
            return contact, None
        return None, None


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
    from library.contact_channels import channel_key, contact_channels
    from library.db.engine import get_session
    from library.contact_addresses import attach_imported_address
    from library.db.models import Contact, ContactCategory, ContactGroup

    session = get_session()

    default_category = session.execute(
        select(ContactCategory).where(ContactCategory.name == "Osoba prywatna")
    ).scalars().first()
    if default_category is None:
        logger.error("Brak kategorii 'Osoba prywatna' w contact_categories — przerywam")
        session.close()
        return

    contacts = list(session.scalars(select(Contact)))
    if not args.apply:
        # Plan on detached snapshots, including birthday changes from earlier rows.
        fields = ("id", "first_name", "last_name", "phone_number", "phone_numbers",
                  "birthday", "birthday_month", "birthday_day", "groups")
        contacts = [SimpleNamespace(**{field: getattr(c, field) for field in fields}) for c in contacts]
    contact_index = _ContactIndex(contacts)

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
    ambiguous_n, birthday_conflicts_n = 0, 0
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

            phone_numbers = _parse_channels(row, "Phone", "phone_numbers")
            email_addresses = _parse_channels(row, "E-mail", "email_addresses")
            email = email_addresses[0]["value"] if email_addresses else None
            phone = phone_numbers[0]["value"] if phone_numbers else None
            company = (row.get("Organization Name") or "").strip() or None
            position = (row.get("Organization Title") or "").strip() or None
            address = (row.get("Address 1 - Formatted") or "").strip() or None
            notes = (row.get("Notes") or "").strip() or None
            birthday_data = _parse_birthday(row.get("Birthday"))
            if (row.get("Birthday") or "").strip() and birthday_data is None:
                skipped_birthday_n += 1
                logger.warning("Wiersz CSV %d: pominięto nieprawidłową datę urodzin", reader.line_num)

            key = " ".join(sorted(normalize_name(f"{first_name or ''} {last_name}")))
            if key:
                seen_keys[key] = seen_keys.get(key, 0) + 1
                if seen_keys[key] > 1:
                    logger.warning("Zduplikowany wpis w CSV (ta sama osoba wystąpiła %d razy): %s %s",
                                    seen_keys[key], first_name, last_name)

            existing, conflict = contact_index.match(phone_numbers, key if first_name else None)
            if conflict:
                ambiguous_n += 1
                logger.warning("CSV row %d skipped: %s", reader.line_num, conflict)
                continue

            if existing:
                matched_n += 1
                birthday_changes, birthday_conflict = _birthday_patch(existing, birthday_data)
                if birthday_conflict:
                    birthday_conflicts_n += 1
                    logger.warning("Wiersz CSV %d: konflikt daty urodzin — zachowano obecną", reader.line_num)
                new_groups = [g for g in group_names if g.lower() not in {eg.name.lower() for eg in existing.groups}]
                logger.info("DOPASOWANO #%s %s %s <- %s %s%s", existing.id, existing.first_name, existing.last_name,
                             first_name, last_name, f" (+grupy: {', '.join(new_groups)})" if new_groups else "")
                if args.apply:
                    changed_fields = []
                    for field, incoming in (("phone_numbers", phone_numbers), ("email_addresses", email_addresses)):
                        current = contact_channels(existing, field)
                        keys = {channel_key(entry["value"], field) for entry in current}
                        additions = [entry for entry in incoming if channel_key(entry["value"], field) not in keys]
                        if additions:
                            setattr(existing, field, current + additions)
                            changed_fields.append(field)
                    if company and not existing.company:
                        existing.company = company
                        changed_fields.append("company")
                    if position and not existing.position:
                        existing.position = position
                        changed_fields.append("position")
                    if attach_imported_address(session, existing, address):
                        changed_fields.append("addresses")
                    for field, value in birthday_changes.items():
                        setattr(existing, field, value)
                        changed_fields.append(field)
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
                    for field, value in birthday_changes.items():
                        setattr(existing, field, value)
                contact_index.add(existing, phone_numbers)
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
                        phone_numbers=phone_numbers,
                        email_addresses=email_addresses,
                        company=company,
                        position=position,
                        **(birthday_data or {}),
                        notes=notes,
                    )
                    for group_name in group_names:
                        contact.groups.append(get_or_create_group(group_name))
                    session.add(contact)
                    session.flush()
                    address_added = attach_imported_address(session, contact, address)
                    record_contact_change(
                        session, contact, "google_import",
                        changed_fields=["first_name", "last_name", "category_id", *(birthday_data or {}),
                                        *(["addresses"] if address_added else [])],
                        note=f"Zaimportowano z eksportu Kontaktów Google ({args.csv})",
                    )
                else:
                    # Index a transient object so dry-run makes the same identity
                    # decisions as --apply, without adding it to the DB session.
                    contact = Contact(first_name=first_name, last_name=last_name,
                                      phone_numbers=phone_numbers, **(birthday_data or {}))
                # New rows may match again by a valid phone, never by name alone.
                contact_index.add(contact)

        if args.apply:
            session.commit()

    session.close()

    print()
    print(f"Wierszy: dopasowanych do istniejących kontaktów: {matched_n}, nowych: {created_n}")
    if skipped_birthday_n:
        print("Pominięto nieprawidłowe daty urodzin — sprawdź ostrzeżenia dla wierszy CSV.")
    if birthday_conflicts_n:
        print("Konflikty dat urodzin: zachowano obecne — sprawdź ostrzeżenia dla wierszy CSV.")
    if ambiguous_n:
        print(f"Niejednoznaczne wiersze pominięte do ręcznego sprawdzenia: {ambiguous_n}")
    if not args.apply:
        print("\n(dry-run — użyj --apply, żeby zapisać zmiany)")


if __name__ == "__main__":
    main()
