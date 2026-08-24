#!/usr/bin/env python3
"""One-off backfill: resolve already-imported WhatsApp neighbor profile Documents
(whatsapp_neighbor_profiles.py) whose sender was only visible as a phone number to
a real name, via an exported Google Contacts CSV — using the same phone-matching
logic (load_contacts/resolve_phone_sender) that script's --contacts-csv option
uses for new/updated documents.

Pure identity backfill: does not touch the WhatsApp export and does not re-run
the LLM extraction/merge pipeline (the stored profile facts are unaffected —
only how the person is displayed changes). For each Document whose byline is
still a bare phone number that resolves via the contacts CSV:
  - title and byline switch from the phone number to the resolved name
  - the "# Sąsiad: <phone>" header in text_md is rewritten to the resolved name
  - a "**Telefon:** <number>" fact line is inserted (if not already present)
  - optionally a "**Mieszkanie:** ..." line too, if --owners-csv resolves an
    apartment for the newly-known name
  - embeddings are regenerated, since text_md content changed

A document whose phone number isn't found in the contacts CSV is left
untouched and listed as unresolved.

Usage:
    cd backend
    python imports/whatsapp_neighbor_profiles_backfill_contacts.py --contacts-csv "../tmp/contacts.csv"              # dry-run
    python imports/whatsapp_neighbor_profiles_backfill_contacts.py --contacts-csv "../tmp/contacts.csv" --apply
    python imports/whatsapp_neighbor_profiles_backfill_contacts.py --contacts-csv "..." --owners-csv "..." --apply
"""

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from imports.whatsapp_neighbor_profiles import (  # noqa: E402
    _embed_document,
    is_phone_number,
    load_contacts,
    load_owners,
    match_owner,
    resolve_phone_sender,
)

logger = logging.getLogger("whatsapp_neighbor_profiles_backfill_contacts")

MIESZKANIE_LINE_PREFIX = "**Mieszkanie:**"
TELEFON_LINE_PREFIX = "**Telefon:**"
WIADOMOSCI_LINE_PREFIX = "**Wiadomości w grupie:**"


def _insert_fact_line(text_md: str, new_line: str, before_prefix: str) -> str | None:
    """Insert new_line as its own line directly before the first line starting with
    before_prefix. Returns None (no-op) if new_line's prefix is already present, or if
    before_prefix isn't found (unexpected text_md shape — caller should report this)."""
    if new_line.split(":", 1)[0] in text_md:
        return text_md
    lines = text_md.split("\n")
    for i, line in enumerate(lines):
        if line.startswith(before_prefix):
            lines.insert(i, new_line)
            return "\n".join(lines)
    return None


def update_document_content(title: str, text_md: str, old_sender: str, new_name: str,
                             phone: str, apartments: list[str] | None) -> tuple[str, str] | None:
    """Returns (new_title, new_text_md), or None if text_md doesn't have the expected shape."""
    old_header = f"# Sąsiad: {old_sender}"
    if old_header not in text_md:
        return None
    new_title = title.replace(f"Sąsiad: {old_sender} (", f"Sąsiad: {new_name} (", 1)
    new_text_md = text_md.replace(old_header, f"# Sąsiad: {new_name}", 1)

    if apartments:
        new_text_md = _insert_fact_line(
            new_text_md, f"{MIESZKANIE_LINE_PREFIX} " + "; ".join(apartments), WIADOMOSCI_LINE_PREFIX
        )
        if new_text_md is None:
            return None
    new_text_md = _insert_fact_line(new_text_md, f"{TELEFON_LINE_PREFIX} {phone}", WIADOMOSCI_LINE_PREFIX)
    if new_text_md is None:
        return None
    return new_title, new_text_md


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--contacts-csv", required=True, help="Eksport Kontaktów Google (CSV)")
    parser.add_argument("--contacts-suffix", default="Tuwima Gardens", help="Sufiks do usunięcia z nazwiska w --contacts-csv")
    parser.add_argument("--owners-csv", default=None, help="Opcjonalny CSV właścicieli mieszkań")
    parser.add_argument("--url-prefix", default="whatsapp://tuwima-gardens/", help="Only Documents whose url starts with this prefix")
    parser.add_argument("--apply", action="store_true", help="Zapisz zmiany (domyślnie: tylko podgląd)")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")

    contacts = load_contacts(args.contacts_csv, args.contacts_suffix)
    logger.info("Wczytano %d numerów telefonów z %s", len(contacts), args.contacts_csv)
    owners = load_owners(args.owners_csv) if args.owners_csv else {}

    from sqlalchemy import select

    from library.config_loader import load_config
    from library.db.engine import get_session
    from library.db.models import Document
    from library.document_repository import DocumentRepository

    session = get_session()
    repo = DocumentRepository(session)
    embedding_model = load_config().require("EMBEDDING_MODEL") if args.apply else None

    docs = list(session.scalars(
        select(Document).where(Document.url.like(f"{args.url_prefix}%")).order_by(Document.id)
    ))
    logger.info("Dokumentów pasujących do prefiksu: %d", len(docs))

    candidates = [d for d in docs if d.byline and is_phone_number(d.byline)]
    if args.limit:
        candidates = candidates[: args.limit]
    logger.info("Kandydatów (nadawca = numer telefonu): %d", len(candidates))

    resolved_n, unresolved_n, shape_mismatch_n, updated_n = 0, 0, 0, 0

    for doc in candidates:
        old_sender = doc.byline
        resolved_name = resolve_phone_sender(old_sender, contacts)
        if not resolved_name:
            unresolved_n += 1
            logger.debug("Nierozwiązany: #%d %s", doc.id, old_sender)
            continue
        resolved_n += 1

        apartments = match_owner(resolved_name, owners) if owners else None
        result = update_document_content(doc.title, doc.text_md or "", old_sender, resolved_name, old_sender, apartments)
        if result is None:
            shape_mismatch_n += 1
            logger.warning("Pomijam #%d %s -> %s: nieoczekiwany kształt text_md", doc.id, old_sender, resolved_name)
            continue
        new_title, new_text_md = result

        logger.info("#%d %s -> %s%s", doc.id, old_sender, resolved_name, f" — {apartments}" if apartments else "")

        if not args.apply:
            continue

        doc.title = new_title
        doc.byline = resolved_name
        doc.text_md = new_text_md
        session.commit()
        repo.embedding_delete(doc.id, embedding_model)
        n = _embed_document(repo, doc, embedding_model)
        session.commit()
        logger.debug("  embeddingi: %d fragmentów", n)
        updated_n += 1

    session.close()

    print()
    print(f"Kandydatów (nadawca = numer telefonu): {len(candidates)}")
    print(f"Rozwiązanych przez contacts-csv: {resolved_n}")
    print(f"Nierozwiązanych (brak w contacts-csv): {unresolved_n}")
    print(f"Pominiętych (nieoczekiwany kształt text_md): {shape_mismatch_n}")
    if args.apply:
        print(f"Zaktualizowano dokumentów: {updated_n}")
    else:
        print("\n(dry-run — użyj --apply, żeby zapisać zmiany)")


if __name__ == "__main__":
    main()
