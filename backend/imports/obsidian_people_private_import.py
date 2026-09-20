#!/usr/bin/env python3
"""Import the reviewed people-private manifest; dry-run unless --apply is given.

Run from backend with PYTHONPATH=. and SECRETS_BACKEND=env plus POSTGRESQL_*
connection variables. The default manifest is deliberately untracked. Source
text stays in memory and, only on apply, in PostgreSQL. Reports contain field
names and presence indicators, never field values or private narrative.

Dry runs disable autoflush and start a PostgreSQL READ ONLY transaction. Apply
locks referenced contacts and groups before checking identities. Conflicting
fields are retained and flagged; ambiguous identities skip the whole operation.
Duplicate sources are retained for separately reviewed removal, never deleted.
"""

import argparse
from collections import Counter
import datetime
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import sys
import unicodedata
from urllib.parse import unquote, urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger("obsidian_people_private_import")
MARKER = "[People-private import 2026-09-14]"
DEFAULT_SPEC = Path(__file__).with_name("_scratch_people_private_import_spec.json")
ACTIONS = {
    "append_existing", "new_contact", "new_contact_exception", "new_contact_multi",
    "merge_duplicates", "merge_into_existing", "split_person", "split_person_primary",
    "skip_empty_file", "skip_no_identifier",
}
FIELDS = ("phone_number", "email", "birthday", "company", "position")
ALIASES = {
    "radek": "radoslaw", "maciek": "maciej", "tomek": "tomasz", "gosia": "malgorzata",
    "gosia tarankowa": "malgorzata tarankowa", "kaska": "katarzyna", "ania": "anna",
}
# Identity spellings/names only, from the reviewed manifest; no vault prose.
# Several existing contacts have incomplete stored names (surname never
# entered, or whole name jammed into one column) — confirmed against these
# ids by phone number cross-check on 2026-09-14, not by guessing.
EXPECTED = {
    116: "Anna Szymańska", 144: "Cichy", 497: "Grzegorz Kocjan",
    203: "Grzegorz", 205: "Grzegorz", 233: "Justa Wodnicka",
    287: "Maciej G", 396: "Radek", 451: "Tomek",
    467: "Wlodzimierz Bartczak",
}
NEW_NAMES = {
    "Lenartowski Łukasz": ("Łukasz", "Lenartowski"),
    "Lewinski Paweł": ("Paweł", "Lewinski"),
    "Lisiak Marcin": ("Marcin", "Lisiak"),
    "Krystyna Valverde Ferreira (Jankowska)": ("Krystyna", "Valverde Ferreira (Jankowska)"),
    "Leo - Syn Krysi i Emanuela": ("Leo", None),
    "Stefański Krzysztof": ("Krzysztof", "Stefański"),
    "KanapkaMan - Rutkowski MAREK Paweł": ("Marek Paweł", "Rutkowski"),
    "Wiktoria od Daniela": ("Wiktoria", None),
    "Skonieczka Rafał": ("Rafał", "Skonieczka"),
    "Jasiak Paweł": ("Paweł", "Jasiak"),
    "Mec Koch Joanna": ("Joanna", "Koch"),
}
LABELS = {
    "telefon": "phone_number", "tel": "phone_number", "phone": "phone_number",
    "phone_number": "phone_number", "email": "email", "e-mail": "email",
    "linkedin": "linkedin_url", "linkedin_url": "linkedin_url",
    "urodziny": "birthday", "birthday": "birthday", "data urodzenia": "birthday",
    "firma": "company", "company": "company", "pracodawca": "company",
    "stanowisko": "position", "position": "position", "adres": "addresses", "address": "addresses",
    "nip": "company",
}
PHONE = re.compile(r"(?:\+48[ -]?)?(?:\d[ -]?){9}")
EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
LINKEDIN = re.compile(r"https?://(?:[\w-]+\.)?linkedin\.com/[^\s<>\])]+", re.I)
MONTHS = dict(zip(
    "stycznia lutego marca kwietnia maja czerwca lipca sierpnia wrzesnia pazdziernika listopada grudnia".split(),
    range(1, 13),
))


def parse_birthday(value):
    """Only complete dates; the Contact Date column cannot represent yearless dates."""
    value = value.strip().rstrip(".")
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        pass
    match = re.fullmatch(r"(\d{1,2})[./](\d{1,2})[./](\d{4})", value)
    if match:
        day, month, year = map(int, match.groups())
        return datetime.date(year, month, day)
    match = re.fullmatch(r"(\d{1,2})\s+([^\W\d_]+)\s+(\d{4})", value)
    if match:
        day, month, year = match.groups()
        return datetime.date(int(year), MONTHS[normalize(month)], int(day))
    raise ValueError("Birthday needs a confirmed day, month and year")


def normalize(value):
    value = unicodedata.normalize("NFKD", value.lower().replace("ł", "l"))
    value = "".join(c for c in value if not unicodedata.combining(c))
    return " ".join(ALIASES.get(t, t) for t in re.findall(r"[a-z]+", value))


def name_matches(contact, expected):
    wanted = set(normalize(expected).split())
    actual = set(normalize(f"{contact.first_name or ''} {contact.last_name or ''} "
                           f"{contact.display_label or ''}").split())
    return bool(wanted) and wanted <= actual


def phone_key(value):
    digits = re.sub(r"\D", "", value or "")
    return digits[2:] if len(digits) == 11 and digits.startswith("48") else digits


def route_fields(body):
    """Extract explicit, standalone facts; keep all other text private.

    Never infer birth years, interpret ages as birthdays, or extract arbitrary
    numbers/URLs from prose (which may describe somebody other than the owner).
    Unsupported dates and overlong/conflicting facts stay private with a flag.
    """
    fields, private, flags = {}, [], []
    for raw in body.splitlines():
        line = raw.strip().lstrip("- ").strip()
        # Markdown links wrapping a URL are still structured facts.
        wrapped = re.fullmatch(r"\[[^\]]*\]\((https?://[^)]+)\)", line)
        if wrapped:
            line = wrapped[1]
        line = re.sub(r"^(urodziny)\s*,\s*", r"\1: ", line, flags=re.I)
        label, sep, value = line.partition(":")
        key = LABELS.get(label.lower()) if sep else None
        value = value.strip() if key else line
        if not key:
            if PHONE.fullmatch(line):
                key = "phone_number"
            elif EMAIL.fullmatch(line):
                key = "email"
            elif LINKEDIN.fullmatch(line):
                key = "linkedin_url"
        if not key:
            if re.search(r"\b(?:pracuje|firma|nip|urodziny|urodzony)\b", line, re.I):
                flags.append("STRUCTURED_PROSE_REVIEW")
            if re.fullmatch(r"\d{1,2}\s+[^\W\d_]+(?:\s+urodziny\.?)?", line, re.I):
                flags.append("BIRTHDAY_UNREPRESENTABLE_WITHOUT_CONFIRMED_DATE")
            private.append(raw)
            continue
        if key == "birthday":
            try:
                value = parse_birthday(value)
            except (ValueError, KeyError):
                flags.append("BIRTHDAY_UNREPRESENTABLE_WITHOUT_CONFIRMED_DATE")
                private.append(raw)
                continue
        elif key in {"phone_number", "email", "linkedin_url"}:
            pattern = {"phone_number": PHONE, "email": EMAIL, "linkedin_url": LINKEDIN}[key]
            if not pattern.fullmatch(value):
                flags.append(f"STRUCTURED_REVIEW:{key}")
                private.append(raw)
                continue
        if label.lower() == "nip":
            value = f"NIP: {value}"
        limit = {"phone_number": 30, "email": 255, "company": 200, "position": 200}.get(key)
        if limit and len(value) > limit:
            flags.append(f"FIELD_TOO_LONG:{key}")
            private.append(raw)
        elif key in fields and fields[key] != value:
            if key == "company" and len(f"{fields[key]}; {value}") <= 200:
                fields[key] = f"{fields[key]}; {value}"
            else:
                flags.append(f"MULTIPLE_VALUES:{key}")
                private.append(raw)
        else:
            fields[key] = value
    return fields, "\n".join(private).strip(), sorted(set(flags))


def route_operation(op, body):
    """Route business records and explicitly attributed multi-person occupations.

    The manifest's business instruction establishes the record's context, not
    the spelling of its values: all values are read from the vault at runtime.
    """
    fields, private, flags = route_fields(body)
    person_fields = {}
    if "NIP/company/address" in op.get("note", ""):
        remaining, company_parts = [], []
        expect_company = False
        for line in private.splitlines():
            stripped = line.strip()
            if normalize(stripped).startswith("zrodlo informacji"):
                expect_company = True
                remaining.append(line)
            elif expect_company and stripped and not stripped.startswith("http"):
                company_parts.append(stripped)
                expect_company = False
            elif re.match(r"^(?:ul\.|al\.|adres:)\s*", stripped, re.I):
                fields["addresses"] = stripped
            elif re.fullmatch(r"[^\W\d_]+\s+(?:\+48[ -]?)?(?:\d[ -]?){9}", stripped):
                fields["phone_number"] = stripped.split(maxsplit=1)[1]
            else:
                remaining.append(line)
        if fields.get("company"):
            company_parts.append(fields["company"])
        company = "; ".join(company_parts)
        if company and len(company) <= 200:
            fields["company"] = company
            private = "\n".join(remaining).strip()
        elif company:
            flags.append("FIELD_TOO_LONG:company")
    if op["action"] == "new_contact_multi":
        for name in op["people"]:
            for line in private.splitlines():
                # A named subject is required; never assign somebody's job to
                # every person sharing a file or infer a job from a pronoun.
                match = re.search(
                    rf"\b{re.escape(name)}\b[^.!?\n]{{0,100}}?\bpracuje\s+(w|jako)\s+([^.!?\n]+)",
                    line, re.I,
                )
                if not match:
                    continue
                key = "company" if match[1].lower() == "w" else "position"
                value = re.split(r"\s+w\s+|,", match[2], maxsplit=1)[0].strip()
                if value and len(value) <= 200:
                    person_fields.setdefault(name, {})[key] = value
        if fields:
            flags.append("MULTI_FIELD_OWNER_UNRESOLVED")
    return fields, private, sorted(set(flags)), person_fields


def append_private(existing, incoming):
    if not incoming or incoming in (existing or ""):
        return existing
    return f"{existing}\n\n{MARKER}\n{incoming}" if existing else incoming


def names_for(op):
    if op["action"] == "new_contact_multi":
        return [(name, None) for name in op["people"]]
    if "new_contact_first_name" in op:
        return [(op["new_contact_first_name"], op.get("new_contact_last_name"))]
    stem = Path(op["path"]).stem
    if stem in NEW_NAMES:
        return [NEW_NAMES[stem]]
    if len(stem.split()) == 1:
        return [(stem, None)]
    raise ValueError("Unreviewed new-contact name layout")


def load_sources(spec_path, vault=None):
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8-sig"))
    root = Path(vault or spec["_meta"]["vault_root"]).resolve()
    repo = Path(__file__).resolve().parents[2]
    if root.is_relative_to(repo):
        raise ValueError("Private vault must be outside the repository")
    sources = {}
    for op in spec["operations"]:
        if op["action"] not in ACTIONS:
            raise ValueError("Unknown manifest action")
        path = (root / op["path"]).resolve()
        if not path.is_relative_to(root):
            raise ValueError("Source path escapes vault")
        sources[op["path"]] = (path.read_text(encoding="utf-8-sig"), path.stat().st_mtime_ns)
    return spec, sources


def open_questions(op):
    """Report codes and identities only; never print the manifest's prose."""
    questions = []
    if op.get("spelling_conflict"):
        questions.append("OPEN #497 Grzegorz Kocian/Kocjan: retain spelling; review")
    if op["action"] == "new_contact_exception":
        questions.append("OPEN new Filip / #116 Anna Szymańska: exception-contact review")
    if op.get("people") == ["Leon", "Marcelina"]:
        questions.append("OPEN Arkadiusz / new Marcelina: no Arkadiusz contact; review")
    return questions


def print_summary(spec, counts):
    print("SPEC_COUNTS " + json.dumps(dict(Counter(o["action"] for o in spec["operations"])), sort_keys=True))
    print("RUN_COUNTS " + json.dumps(dict(counts), sort_keys=True))


def report_unavailable(spec, sources):
    for name in spec["groups"]["new_groups_to_create"]:
        print(f"GROUP {name}: intended=create if absent; current=UNVERIFIED")
    for op in spec["operations"]:
        fields, private, flags, per_person = route_operation(op, sources[op["path"]][0])
        create_n = len(names_for(op)) if op["action"] in {
            "new_contact", "new_contact_exception", "new_contact_multi", "split_person",
        } else 0
        print(f"FILE {op['path']} | action={op['action']} | current=UNAVAILABLE | "
              f"intended=manifest operation; create_contacts={create_n}; fields={sorted(fields)}; "
              f"person_fields={{{', '.join(f'{name}: {sorted(values)}' for name, values in per_person.items())}}}; "
              f"private_payload={'present' if private else 'empty'}; NOT EXECUTED | "
              f"FLAG=DATABASE_UNAVAILABLE; routing_flags={flags}")
        for question in open_questions(op):
            print(question)
    print_summary(spec, {"unverified": len(spec["operations"]), "writes": 0})


def run_import(session, spec, sources, apply=False):
    from sqlalchemy import select, text

    from library.contact_change_log import record_contact_change
    from library.address_formatting import format_address, imported_address_fields
    from library.contact_addresses import attach_imported_address, contact_address_links
    from library.db.models import Address, Contact, ContactAddress, ContactCategory, ContactChangeLog, ContactGroup, ContactLink, ContactRelationship

    session.autoflush = False
    counts = Counter()
    # This must be the first statement, before even loading category metadata.
    if not apply:
        session.execute(text("SET TRANSACTION READ ONLY"))
    else:
        # Serialize this importer (other editors are protected by row locks).
        session.execute(text("SELECT pg_advisory_xact_lock(20260914, 1)"))

    def fresh(model, row_id):
        stmt = select(model).where(model.id == row_id).execution_options(populate_existing=True)
        if apply:
            stmt = stmt.with_for_update()
        return session.scalars(stmt).one_or_none()

    def verify(row_id, expected, identity_body=""):
        contact = fresh(Contact, row_id)
        matches = contact is not None and name_matches(contact, expected)
        # The organization-titled file has no person name in its filename.
        # Require both live name parts to occur in its personal LinkedIn slug;
        # this validates the spec's IDs without searching for replacement IDs.
        if contact is not None and not matches and expected == "OpenStreetMap":
            actual = normalize(f"{contact.first_name or ''} {contact.last_name or ''}").split()
            for url in LINKEDIN.findall(identity_body):
                slug = normalize(unquote(urlparse(url).path.removeprefix("/in/"))).split()
                matches = len(actual) >= 2 and set(actual) <= set(slug)
                if matches:
                    break
        if not matches:
            # The unexpected record's data is deliberately not disclosed.
            print(f"FLAG ID_CAVEAT #{row_id} expected={expected}: missing/wrong/unverifiable; SKIP")
            counts["id_caveat"] += 1
            return None
        if row_id == 116 and not contact.first_name:
            print("FLAG NAME_LAYOUT #116 Anna Szymańska: review; retain existing name fields")
        return contact

    category = session.scalars(select(ContactCategory).where(ContactCategory.name == "Osoba prywatna")).one_or_none()
    if category is None:
        raise ValueError("Missing category Osoba prywatna")
    groups, bad_groups = {}, set()
    for name, row_id in spec["groups"]["existing_reused"].items():
        group = fresh(ContactGroup, row_id)
        if group is None or group.name != name:
            print(f"FLAG GROUP_DRIFT #{row_id} {name}: dependent operations skipped")
            bad_groups.add(name)
        else:
            groups[name] = group
            print(f"GROUP #{row_id} {name}: verified; reuse")
    for name in spec["groups"]["new_groups_to_create"]:
        stmt = select(ContactGroup).where(ContactGroup.name == name)
        if apply:
            stmt = stmt.with_for_update()
        matches = list(session.scalars(stmt))
        if len(matches) > 1:
            print(f"FLAG GROUP_AMBIGUOUS {name}: dependent operations skipped")
            bad_groups.add(name)
            continue
        group = matches[0] if matches else None
        print(f"GROUP {name}: {'reuse existing' if group else 'create'}")
        if group is None:
            counts["groups_to_create"] += 1
            if apply:
                group = ContactGroup(name=name)
                session.add(group)
                session.flush()
        groups[name] = group

    vocabulary = set(session.scalars(select(ContactRelationship.relationship_type).distinct()))
    resolved = {}
    # Pair notes are applied oldest first, so the last private entry is current.
    operations = list(spec["operations"])
    paired = sorted((o for o in operations if o.get("contact_id") == 205), key=lambda o: sources[o["path"]][1])
    pair_iter = iter(paired)
    operations = [next(pair_iter) if o.get("contact_id") == 205 else o for o in operations]
    if paired:
        print(f"PAIR #205: retain both private source texts; current source={paired[-1]['path']} (mtime)")

    def audit(contact, fields, note):
        record_contact_change(session, contact, "obsidian_import", changed_fields=sorted(set(fields)), note=note)

    def linkedin_links(contact):
        if contact.id is None:
            return []
        return list(session.scalars(select(ContactLink).where(
            ContactLink.contact_id == contact.id, ContactLink.link_type == "linkedin",
        ).order_by(ContactLink.id)))

    def update(contact, fields, private, group_name, op, token, secondary=None):
        changes, flags = {}, []
        links = linkedin_links(contact)
        address_links = contact_address_links(session, contact)
        known_addresses = {format_address(link.address) for link in address_links}
        incoming_address = (fields.get("addresses") or "").strip()
        incoming_formatted = (
            format_address(Address(**imported_address_fields(incoming_address))) if incoming_address else ""
        )
        if incoming_address and incoming_formatted not in known_addresses:
            changes["addresses"] = [incoming_address]
            known_addresses.add(incoming_formatted)
        shared_addresses = []
        linkedin_url = fields.get("linkedin_url")
        if linkedin_url and not any(link.url == linkedin_url for link in links):
            if not links:
                changes["links"] = linkedin_url
            else:
                flags.append("FIELD_CONFLICT:linkedin_url:retain")
        for key, value in fields.items():
            if key in {"linkedin_url", "addresses"}:
                continue
            current = getattr(contact, key)
            if not current:
                changes[key] = value
            elif current != value:
                flags.append(f"FIELD_CONFLICT:{key}:retain")
        merged_private = append_private(contact.private_notes, private)
        if secondary:
            for link in contact_address_links(session, secondary):
                if format_address(link.address) not in known_addresses:
                    shared_addresses.append(link.address)
                    known_addresses.add(format_address(link.address))
            if shared_addresses:
                changes.setdefault("addresses", [])
            secondary_links = linkedin_links(secondary)
            target_url = changes.get("links") or (links[0].url if links else None)
            for link in secondary_links:
                if not target_url:
                    changes["links"] = target_url = link.url
                elif link.url != target_url:
                    flags.append("MERGE_CONFLICT:links:retain")
            for key in FIELDS:
                value = getattr(secondary, key)
                if value and not getattr(contact, key) and key not in changes:
                    changes[key] = value
                elif value and value != changes.get(key, getattr(contact, key)):
                    flags.append(f"MERGE_CONFLICT:{key}:retain")
            merged_private = append_private(merged_private, secondary.private_notes or "")
            merged_private = append_private(merged_private, secondary.notes or "")
            print(f"FLAG MERGE_RETAIN_SECONDARY #{secondary.id}: copy nonconflicting fields/groups; "
                  "review remaining metadata/relationships and removal separately")
        if merged_private != contact.private_notes:
            changes["private_notes"] = merged_private
        if op["action"] == "split_person_primary" and contact.last_name != op["fix_last_name_to"]:
            changes["last_name"] = op["fix_last_name_to"]
        add_groups = []
        existing_groups = {g.name for g in contact.groups}
        if group_name and group_name not in existing_groups:
            add_groups.append(group_name)
        if secondary:
            for group in secondary.groups:
                if group.name not in existing_groups and group.name not in add_groups:
                    add_groups.append(group.name)
                    groups[group.name] = group
        occupied = [key for key in FIELDS if getattr(contact, key)] + (["links"] if links else []) + (["addresses"] if address_links else [])
        print(f"  CONTACT #{contact.id or 'new'} {contact.first_name or ''} {contact.last_name or ''}: "
              f"current_fields={occupied}, private_notes={'present' if contact.private_notes else 'empty'}, "
              f"groups={sorted(existing_groups)}; intended_fields={sorted(changes)}, "
              f"add_groups={add_groups}; flags={flags}")
        if apply:
            for key, value in changes.items():
                if key == "addresses":
                    for address_text in value:
                        attach_imported_address(session, contact, address_text)
                    for address in shared_addresses:
                        has_addresses = bool(contact_address_links(session, contact))
                        session.add(ContactAddress(contact=contact, address=address,
                                                   role="zamieszkania", is_primary=not has_addresses))
                        session.flush()
                elif key == "links":
                    if links:
                        links[0].url = value
                    else:
                        session.add(ContactLink(contact_id=contact.id, link_type="linkedin", url=value))
                else:
                    setattr(contact, key, value)
            for name in add_groups:
                contact.groups.append(groups[name])
            changed_fields = list(changes) + (["groups"] if add_groups else [])
            if changed_fields:
                audit(contact, changed_fields, token)
                session.flush()
        counts["contacts_to_update"] += bool(changes or add_groups)

    for op in operations:
        path, action = op["path"], op["action"]
        print(f"FILE {path} | action={action}")
        for question in open_questions(op):
            print(question)
        if action.startswith("skip_"):
            print("  current=source inspected; intended=no change (reviewed skip)")
            counts["skipped_by_spec"] += 1
            continue
        group_name = op.get("ensure_group")
        if group_name in bad_groups:
            print("  FLAG GROUP_DRIFT: SKIP operation")
            counts["skipped_flagged"] += 1
            continue
        body = sources[path][0]
        fields, private, flags, per_person = route_operation(op, body)
        print(f"  source_fields={sorted(fields)}; private_payload={'present' if private else 'empty'}; flags={flags}")
        contact = secondary = relative = None
        row_id = op.get("contact_id", op.get("primary_contact_id"))
        expected = EXPECTED.get(row_id, Path(path).stem)
        if row_id is not None:
            contact = verify(row_id, expected, body)
            if contact is None:
                counts["skipped_flagged"] += 1
                continue
        if action == "merge_duplicates":
            secondary = verify(op["secondary_contact_id"], expected, body)
            if secondary is None:
                counts["skipped_flagged"] += 1
                continue
        reference = op.get("relationship_to_existing", {})
        relative_id = op.get("split_of_contact_id", reference.get("contact_id"))
        if relative_id:
            relative = verify(relative_id, EXPECTED.get(relative_id, ""))
            if relative is None:
                counts["skipped_flagged"] += 1
                continue
            resolved[f"id:{relative_id}"] = [relative]
        if action == "append_existing" and row_id is None:
            # Only manifest entries explicitly requesting live matching use this.
            candidates = [c for c in session.scalars(select(Contact)) if name_matches(c, expected)]
            phone = fields.get("phone_number")
            if phone:
                candidates = [c for c in candidates if phone_key(c.phone_number) == phone_key(phone)]
            elif len(normalize(expected).split()) < 2:
                candidates = []  # Bare names are never an identity key.
            if len(candidates) != 1:
                print(f"  FLAG LIVE_MATCH_UNVERIFIED {expected}: SKIP (name/phone not unique)")
                counts["skipped_flagged"] += 1
                continue
            contact = verify(candidates[0].id, expected)
            if contact is None or (phone and phone_key(contact.phone_number) != phone_key(phone)):
                print("  FLAG LIVE_MATCH_CHANGED: SKIP")
                counts["skipped_flagged"] += 1
                continue
        token = "people-private:2026-09-14:" + hashlib.sha256(path.encode()).hexdigest()
        if action in {"new_contact", "new_contact_exception", "new_contact_multi", "split_person"}:
            people = []
            for index, (first, last) in enumerate(names_for(op)):
                person_token = f"{token}:{index}"
                ids = set(session.scalars(select(ContactChangeLog.contact_id).where(
                    ContactChangeLog.source == "obsidian_import", ContactChangeLog.note == person_token,
                )))
                if len(ids) > 1:
                    print(f"  FLAG IMPORT_PROVENANCE_AMBIGUOUS {first} {last or ''}: SKIP")
                    people.append(None)
                    continue
                person = verify(next(iter(ids)), f"{first or ''} {last or ''}") if ids else None
                if ids and person is None:
                    people.append(None)
                    continue
                if person is None:
                    person = Contact(first_name=first, last_name=last, category_id=category.id)
                    print(f"  current=absent in import provenance; intended=create {first} {last or ''}")
                    counts["contacts_to_create"] += 1
                    if apply:
                        session.add(person)
                        session.flush()
                        audit(person, ["first_name", "last_name", "category_id"], person_token)
                # Shared context is private. Unattributed structured facts in a
                # multi-person file must not be assigned to every person.
                person_fields = fields if action != "new_contact_multi" else per_person.get(first, {})
                if action == "new_contact_multi" and fields:
                    print("  FLAG MULTI_FIELD_OWNER_UNRESOLVED: retain facts privately pending attribution")
                person_private = body if action == "new_contact_multi" else private
                # Only this explicit manifest instruction permits recording an
                # uncertain hint. Other guesses remain report-only.
                if "relationship_hint in private_notes" in op.get("note", ""):
                    hint = re.search(r"([^.]*?\blikely\b[^.—]+)", op["note"])
                    if hint:
                        person_private = append_private(person_private, "Unconfirmed relationship hint: " + hint[1].strip())
                update(person, person_fields, person_private, group_name, op, person_token)
                people.append(person)
            resolved[path] = people
        else:
            # The reviewed #205 pair explicitly requires both complete texts.
            update(contact, fields, body if row_id == 205 else private, group_name, op, token, secondary)
            resolved[path] = [contact]
        counts[action] += 1

    # Each edge below is explicitly authorized by the corresponding manifest
    # note/hint. No edges for guessed family links or friendship cross-links.
    edges = []
    def link(source_path, source_index, target_path, target_index, kind):
        sources_ = resolved.get(source_path, [])
        targets_ = resolved.get(target_path, [])
        if (source_index >= len(sources_) or target_index >= len(targets_)
                or sources_[source_index] is None or targets_[target_index] is None):
            print(f"FLAG RELATIONSHIP_ENDPOINT_UNRESOLVED: {source_path} / {target_path}")
            return
        edges.append((sources_[source_index], targets_[target_index], kind))

    by_stem = {Path(o["path"]).stem: o for o in operations}
    def hinted(stem):
        op = by_stem.get(stem, {})
        return op.get("relationship_hint") or op.get("relationship_type_hint") or op.get("relationship_to_existing")

    if hinted("Emanuel") and hinted("Krystyna Valverde Ferreira (Jankowska)"):
        link(by_stem["Emanuel"]["path"], 0, by_stem["Krystyna Valverde Ferreira (Jankowska)"]["path"], 0, "żona")
    if hinted("Leo - Syn Krysi i Emanuela"):
        for parent, kind in [("Emanuel", "ojciec"), ("Krystyna Valverde Ferreira (Jankowska)", "matka")]:
            if parent in by_stem:
                link(by_stem["Leo - Syn Krysi i Emanuela"]["path"], 0, by_stem[parent]["path"], 0, kind)
    if hinted("Alicja"):
        link("id:144", 0, by_stem["Alicja"]["path"], 0, "partnerka")
    if hinted("Filip"):
        link(by_stem["Filip"]["path"], 0, "id:116", 0, "matka")
    for op in operations:
        if op.get("people") == ["Kaśka", "Franek", "Hanka", "Marek"] and op.get("note"):
            link(op["path"], 0, op["path"], 1, "syn")
            link(op["path"], 0, op["path"], 2, "córka")
            link(op["path"], 0, op["path"], 3, "mąż")
        if op.get("people") == ["Marcin", "Emilia", "Julka"] and op.get("note"):
            link(op["path"], 0, op["path"], 2, "córka")
            link(op["path"], 1, op["path"], 2, "córka")
    for source, target, kind in edges:
        existing = None
        if source.id and target.id:
            existing = session.scalars(select(ContactRelationship).where(
                ContactRelationship.contact_id == source.id, ContactRelationship.related_contact_id == target.id,
                ContactRelationship.relationship_type == kind,
            )).first()
        print(f"RELATIONSHIP #{source.id or 'new'} {source.first_name or ''} -> "
              f"#{target.id or 'new'} {target.first_name or ''}: {kind}; "
              f"{'exists' if existing else 'create'}; vocabulary={'existing' if kind in vocabulary else 'new explicit label'}")
        if not existing:
            counts["relationships_to_create"] += 1
            if apply:
                session.add(ContactRelationship(contact_id=source.id, related_contact_id=target.id, relationship_type=kind))
                for person in (source, target):
                    audit(person, ["relationships"], "People-private import 2026-09-14: explicit relationship")
    if apply:
        session.commit()
    else:
        session.rollback()
    print_summary(spec, counts)
    print("APPLIED" if apply else "DRY-RUN: no database writes; --apply required to save")
    return counts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument("--vault", type=Path, help="Private source vault (outside repository)")
    parser.add_argument("--apply", action="store_true", help="Zapisz zmiany (domyślnie: tylko podgląd)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    # Never enable SQL echo: exception messages/SQL parameters can contain notes.
    logging.getLogger("sqlalchemy.engine").setLevel(logging.CRITICAL)
    from library.db.engine import get_session
    from sqlalchemy.exc import SQLAlchemyError

    session = None
    spec = None
    try:
        spec, sources = load_sources(args.spec, args.vault)
        session = get_session()
        run_import(session, spec, sources, apply=args.apply)
        return 0
    except Exception as exc:
        if session is not None:
            session.rollback()
        # Do not print exception text or traceback (may include SQL parameters).
        logger.error("Import failed (%s); transaction rolled back; private details suppressed", type(exc).__name__)
        if spec is not None and not args.apply and isinstance(exc, SQLAlchemyError):
            report_unavailable(spec, sources)
        return 1
    finally:
        if session is not None:
            session.close()


if __name__ == "__main__":
    sys.exit(main())
