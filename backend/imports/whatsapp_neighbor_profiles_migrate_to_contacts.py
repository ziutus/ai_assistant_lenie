#!/usr/bin/env python3
"""One-off migration: move every pre-existing WhatsApp neighbor-profile
Document (created by the old Document-based whatsapp_neighbor_profiles.py —
title "Sąsiad: ... (...)", synthetic url "whatsapp://<group>/osoba/<slug>")
onto the matching Contact's `whatsapp_profile` column, then delete the
Document. This removes the duplicate place a neighbor's info had to be
looked up in (Document vs. the private Contact book) — see
feature/contact-groups-and-google-contacts-import and
feedback_no_merge_unverifiable_contacts.md for the matching-safety rule this
follows (phone match first, name match second, never merge a same-run
same-name-no-phone collision).

Re-running whatsapp_neighbor_profiles.py against the original WhatsApp
export .txt (still on disk) always regenerates this data from scratch if
something here goes wrong — the Documents are not the only copy of the
underlying facts, so deleting them after a successful migration is safe.

Usage:
    cd backend
    python imports/whatsapp_neighbor_profiles_migrate_to_contacts.py                        # dry-run
    python imports/whatsapp_neighbor_profiles_migrate_to_contacts.py --apply
"""

import argparse
import json
import logging
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from imports.whatsapp_neighbor_profiles import (  # noqa: E402
    find_or_create_contact, is_phone_number, load_contact_name_index, load_contact_phone_index,
    normalize_name, update_whatsapp_profile,
)

logger = logging.getLogger("whatsapp_neighbor_profiles_migrate_to_contacts")

_PROFILE_JSON_MARKER_START = "<!-- lenie-neighbor-profile-json"
_PROFILE_JSON_MARKER_END = "-->"
_FRONT_MATTER_RE = re.compile(
    re.escape(_PROFILE_JSON_MARKER_START) + r"\n(.*?)\n" + re.escape(_PROFILE_JSON_MARKER_END), re.DOTALL,
)
_TELEFON_RE = re.compile(r"\*\*Telefon:\*\* (.+)$", re.MULTILINE)
_STATS_RE = re.compile(r"\*\*Wiadomości w grupie:\*\* (\d+) \(od (.+?) do (.+?)\)")
_GROUP_LABEL_RE = re.compile(r"^Sąsiad: .+ \((.+)\)$")
_URL_GROUP_SLUG_RE = re.compile(r"^whatsapp://(.+)/osoba/[^/]+$")


def _load_legacy_state(text_md: str | None) -> dict | None:
    if not text_md:
        return None
    m = _FRONT_MATTER_RE.search(text_md)
    if not m:
        return None
    try:
        state = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    if not isinstance(state, dict):
        return None
    if "profile" not in state and "last_processed_at" not in state:
        return {"profile": state, "last_processed_at": None}
    return state


def _extract_phone(byline: str | None, text_md: str) -> str | None:
    if byline and is_phone_number(byline):
        return byline
    m = _TELEFON_RE.search(text_md)
    return m.group(1).strip() if m else None


def _extract_stats(text_md: str) -> dict:
    m = _STATS_RE.search(text_md)
    if not m:
        return {"message_count": 0, "first_date": "", "last_date": ""}
    return {"message_count": int(m.group(1)), "first_date": m.group(2), "last_date": m.group(3)}


def _extract_group_label(title: str, fallback: str) -> str:
    m = _GROUP_LABEL_RE.match(title or "")
    return m.group(1) if m else fallback


def _predict_match(display_name: str, phone: str | None, phone_index: dict, name_index: dict) -> bool:
    """Read-only preview of find_or_create_contact()'s matching decision, for dry-run."""
    if phone:
        import re as _re

        digits = _re.sub(r"\D", "", phone)
        if digits in phone_index or digits[-9:] in phone_index:
            return True
    key = " ".join(sorted(normalize_name(display_name)))
    return bool(key and key in name_index)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url-prefix", default="whatsapp://", help="Tylko dokumenty, których url zaczyna się od tego prefiksu")
    parser.add_argument("--contact-group", default="Tuwima Gardens Mieszkańcy", help="Grupa kontaktów, do której trafiają dopasowani/nowi sąsiedzi")
    parser.add_argument("--apply", action="store_true", help="Zapisz zmiany i usuń dokumenty (domyślnie: tylko podgląd)")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")

    from sqlalchemy import select

    from library.db.engine import get_session
    from library.db.models import ContactCategory, ContactGroup, Document
    from library.document_service import DocumentService

    session = get_session()

    default_category = session.execute(
        select(ContactCategory).where(ContactCategory.name == "Osoba prywatna")
    ).scalars().first()
    if default_category is None:
        logger.error("Brak kategorii 'Osoba prywatna' w contact_categories — przerywam")
        session.close()
        return

    contact_group = session.execute(
        select(ContactGroup).where(ContactGroup.name == args.contact_group)
    ).scalars().first()
    if contact_group is None:
        contact_group = ContactGroup(name=args.contact_group)
        session.add(contact_group)
        session.flush()

    docs = list(session.scalars(
        select(Document).where(Document.document_type == "text", Document.url.like(f"{args.url_prefix}%"))
        .order_by(Document.id)
    ))
    if args.limit:
        docs = docs[: args.limit]
    logger.info("Dokumentów do migracji: %d", len(docs))

    phone_index = load_contact_phone_index(session)
    name_index = load_contact_name_index(session)
    service = DocumentService(session)

    matched_existing_n, created_n, unparsable_n = 0, 0, 0

    for doc in docs:
        text_md = doc.text_md or ""
        group_slug_match = _URL_GROUP_SLUG_RE.match(doc.url or "")
        if not group_slug_match:
            unparsable_n += 1
            logger.warning("Pomijam #%d: url nie pasuje do wzorca whatsapp://<grupa>/osoba/<slug>: %s", doc.id, doc.url)
            continue
        group_slug = group_slug_match.group(1)
        group_label = _extract_group_label(doc.title or "", group_slug)

        legacy_state = _load_legacy_state(text_md)
        profile = (legacy_state or {}).get("profile")
        last_processed_at = (legacy_state or {}).get("last_processed_at")

        display_name = doc.byline or (doc.title or "").removeprefix("Sąsiad: ").split(" (")[0]
        phone = _extract_phone(doc.byline, text_md)
        stats = _extract_stats(text_md)

        if not args.apply:
            would_match = _predict_match(display_name, phone, phone_index, name_index)
            if would_match:
                matched_existing_n += 1
                logger.info("[DRY-RUN] DOPASOWANO <- dok. #%d: %s", doc.id, display_name)
            else:
                created_n += 1
                logger.info("[DRY-RUN] NOWY KONTAKT <- dok. #%d: %s", doc.id, display_name)
            continue

        contact, is_new = find_or_create_contact(session, display_name, phone, default_category.id,
                                                   phone_index, name_index)
        if contact_group not in contact.groups:
            contact.groups.append(contact_group)
        update_whatsapp_profile(contact, group_slug, group_label, profile, [], stats, last_processed_at or "")
        session.commit()
        service.delete_document(doc.id)
        session.commit()

        if is_new:
            created_n += 1
            logger.info("NOWY KONTAKT #%d z dok. #%d: %s", contact.id, doc.id, display_name)
        else:
            matched_existing_n += 1
            logger.info("DOPASOWANO kontakt #%d <- dok. #%d: %s", contact.id, doc.id, display_name)

    session.close()

    print()
    print(f"Dokumentów przetworzonych: {len(docs)}")
    print(f"Dopasowanych do istniejących kontaktów: {matched_existing_n}")
    print(f"Nowych kontaktów: {created_n}")
    print(f"Nieparsowalnych (pominiętych): {unparsable_n}")
    if not args.apply:
        print("\n(dry-run — użyj --apply, żeby zapisać zmiany i usunąć dokumenty)")


if __name__ == "__main__":
    main()
