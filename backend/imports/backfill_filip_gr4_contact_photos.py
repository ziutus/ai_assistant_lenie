#!/usr/bin/env python3
"""One-off: upload profile photos for members of the "Przedszkole - Filip gr. 4"
contact_groups group (see google_contacts_import.py / project memory
project_filip_gr4_contacts_import) from a local directory of image files.

Each file is expected to be named "<bare name>.<ext>" or
"<bare name> - Filip gr 4.<ext>" (same naming convention the Google Contacts
CSV used before suffix-stripping — see google_contacts_import.py), matched
case-insensitively against the group's contacts by "first_name last_name" (or
bare last_name for the several members with no known surname). Ambiguous or
unmatched files are reported and skipped rather than guessed.

Uses the same storage path as the REST photo upload
(POST /contacts/<id>/photo, contact_routes.py): ObjectStorage.put_bytes()
under contacts/<uuid>/photo<ext>, then Contact.photo_storage_key.

Usage:
    cd backend
    python imports/backfill_filip_gr4_contact_photos.py --dir "../tmp/filip-gr-4"           # dry-run
    python imports/backfill_filip_gr4_contact_photos.py --dir "../tmp/filip-gr-4" --apply
"""

import argparse
import datetime
import logging
import mimetypes
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger("backfill_filip_gr4_contact_photos")

GROUP_NAME = "Przedszkole - Filip gr. 4"
SUFFIX_RE = re.compile(r"\s*-\s*Filip gr 4\s*$", re.IGNORECASE)
ALLOWED_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif"})


def _normalize(name: str) -> str:
    return " ".join(name.lower().split())


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", required=True, help="Katalog ze zdjęciami")
    parser.add_argument("--apply", action="store_true", help="Zapisz zmiany (domyślnie: tylko podgląd)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")

    from sqlalchemy import select

    from library.contact_change_log import record_contact_change
    from library.config_loader import load_config
    from library.db.engine import get_session
    from library.db.models import Contact, ContactGroup
    from library.storage import storage_from_config

    session = get_session()

    group = session.execute(select(ContactGroup).where(ContactGroup.name == GROUP_NAME)).scalars().first()
    if group is None:
        logger.error("Brak grupy %r — przerywam", GROUP_NAME)
        session.close()
        return

    by_name: dict[str, Contact] = {}
    for c in group.contacts:
        key = _normalize(f"{c.first_name or ''} {c.last_name}")
        by_name[key] = c
        if not c.first_name:
            by_name[_normalize(c.last_name)] = c

    storage = storage_from_config(load_config())

    photo_dir = Path(args.dir)
    files = sorted(p for p in photo_dir.iterdir() if p.is_file())

    matched_n, skipped_n, replaced_n = 0, 0, 0

    for path in files:
        extension = path.suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            logger.warning("POMIJAM (nieobsługiwane rozszerzenie): %s", path.name)
            skipped_n += 1
            continue

        bare_name = SUFFIX_RE.sub("", path.stem).strip()
        key = _normalize(bare_name)
        contact = by_name.get(key)
        if contact is None:
            logger.warning("POMIJAM (brak dopasowania w grupie): %s (szukano: %r)", path.name, bare_name)
            skipped_n += 1
            continue

        matched_n += 1
        already_has_photo = bool(contact.photo_storage_key)
        logger.info(
            "%s#%d %s %s <- %s%s",
            "PODMIENIAM" if already_has_photo else "DOPASOWANO",
            contact.id, contact.first_name or "", contact.last_name, path.name,
            " (już ma zdjęcie)" if already_has_photo else "",
        )
        if already_has_photo:
            replaced_n += 1

        if args.apply:
            data = path.read_bytes()
            content_type = mimetypes.guess_type(path.name)[0]
            storage_key = f"contacts/{contact.uuid}/photo{extension}"
            storage.put_bytes(storage_key, data, content_type=content_type)
            contact.photo_storage_key = storage_key
            contact.updated_at = datetime.datetime.now()
            record_contact_change(
                session, contact, "manual_edit", changed_fields=["photo_storage_key"],
                note=f"Zdjęcie profilowe dodane z {path.name} (backfill_filip_gr4_contact_photos.py)",
            )

    if args.apply:
        session.commit()

    session.close()

    print()
    print(f"Dopasowanych: {matched_n} (w tym podmienionych istniejących: {replaced_n}), pominiętych: {skipped_n}")
    if not args.apply:
        print("\n(dry-run — użyj --apply, żeby zapisać zmiany)")


if __name__ == "__main__":
    main()
