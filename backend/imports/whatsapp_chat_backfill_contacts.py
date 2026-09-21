#!/usr/bin/env python3
"""One-off backfill: re-resolve chat_messages.contact_id for messages imported before
whatsapp_chat_import.py stripped the household's WhatsApp display-name convention
(a trailing " - <suffix>" community tag, e.g. " - Tuwima Gardens") before matching a
sender against the private contact book. Contacts there never carry that suffix
(google_contacts_import.py strips it at import time), so every affected sender's
normalized-name key never matched and contact_id was left NULL — confirmed on the
"Tuwima Gardens - Czat ogólny" import, where senders like "Wojtek Szot - Tuwima
Gardens" had a matching, unambiguous contact in the book but were never linked.

Only touches rows with contact_id IS NULL — never overwrites an existing resolution.
Uses the same resolve-only library.whatsapp_parser.find_contact() the importer uses
(phone first, then normalized name; ambiguous same-name contacts are never guessed,
see feedback_no_merge_unverifiable_contacts.md), so a sender that's genuinely
ambiguous or unknown stays unresolved here too.

Data access: ORM (SQLAlchemy) via get_session(), only when --apply is passed.

Usage:
    cd backend
    python imports/whatsapp_chat_backfill_contacts.py --chat-key "tuwima-gardens/czat-ogolny"
    python imports/whatsapp_chat_backfill_contacts.py --chat-key "..." --apply
    python imports/whatsapp_chat_backfill_contacts.py --chat-key "..." --sender-suffix "Inna Grupa" --apply
    python imports/whatsapp_chat_backfill_contacts.py --chat-key "..." -v
"""

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from library.whatsapp_parser import (  # noqa: E402
    find_contact,
    is_phone_number,
    load_contact_name_index,
    load_contact_phone_index,
    strip_sender_suffix,
)

logger = logging.getLogger("whatsapp_chat_backfill_contacts")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--chat-key", required=True, help="chat_conversations.chat_key do przetworzenia")
    parser.add_argument("--sender-suffix", default="Tuwima Gardens",
                        help="Sufiks ' - <suffix>' do odcięcia przed dopasowaniem (pusty string wyłącza)")
    parser.add_argument("--apply", action="store_true", help="Zapisz zmiany (domyślnie: tylko podgląd)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")

    from sqlalchemy import select

    from library.db.engine import get_session
    from library.db.models import ChatConversation, ChatMessage

    session = get_session()
    try:
        conversation = session.execute(
            select(ChatConversation).where(ChatConversation.chat_key == args.chat_key)
        ).scalars().first()
        if conversation is None:
            print(f"Nie znaleziono rozmowy o chat_key={args.chat_key!r}")
            return

        phone_index = load_contact_phone_index(session)
        name_index = load_contact_name_index(session)
        suffix = args.sender_suffix or None

        rows = session.scalars(
            select(ChatMessage).where(
                ChatMessage.conversation_id == conversation.id,
                ChatMessage.contact_id.is_(None),
            )
        ).all()

        matched_by_sender: dict[str, int] = {}
        matched_count = 0
        for msg in rows:
            phone = msg.sender_name_raw if is_phone_number(msg.sender_name_raw) else None
            sender_for_match = strip_sender_suffix(msg.sender_name_raw, suffix)
            contact_id = find_contact(sender_for_match, phone, phone_index, name_index)
            if contact_id is None:
                continue
            matched_count += 1
            matched_by_sender[msg.sender_name_raw] = contact_id
            if args.apply:
                msg.contact_id = contact_id

        print(f"Rozmowa #{conversation.id} „{conversation.display_name}”")
        print(f"Wiadomości bez kontaktu przed backfillem: {len(rows)}")
        print(f"Dopasowanych po odcięciu sufiksu {suffix!r}: {matched_count}")
        if args.verbose:
            for sender, contact_id in sorted(matched_by_sender.items()):
                logger.debug("%-50s -> contact_id=%d", sender, contact_id)

        if args.apply:
            session.commit()
            print(f"Zaktualizowano contact_id dla {matched_count} wiadomości.")
        else:
            print("[DRY-RUN] Nic nie zapisano — użyj --apply.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
