#!/usr/bin/env python3
"""One-off backfill: give synced WhatsApp messages that carry only a phone number as the sender
label (history-sync messages have no push name) the name the bridge's contact store knows now.

Only touches ``chat_messages`` rows with ``source='sync'``, not from the owner, whose
``sender_name_raw`` is a bare number or a ``WhatsApp <id>`` placeholder; a sender the bridge knows
no name for stays as it is. ``contact_id`` and message text are never changed. Needs the bridge
(``WHATSAPP_BRIDGE_URL``/``WHATSAPP_BRIDGE_TOKEN`` in the config), so run it inside the
``lenie-ai-server`` container on the NAS (``docker cp`` the script in, like the other chat backfills).

Usage:
    cd backend
    python imports/whatsapp_chat_backfill_names.py            # dry-run: one line per sender
    python imports/whatsapp_chat_backfill_names.py --apply
"""

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger("whatsapp_chat_backfill_names")

_NUMERIC_LABEL = r"^(\+?[0-9 ]+|WhatsApp .*)$"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Zapisz zmiany (domyślnie: tylko podgląd)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")

    from sqlalchemy import func, select, update

    from library.chat_contact_service import bridge_name
    from library.config_loader import load_config
    from library.db.engine import get_session
    from library.db.models import ChatMessage
    from library.whatsapp_sync_service import BridgeClient

    config = load_config()
    url, token = config.get("WHATSAPP_BRIDGE_URL"), config.get("WHATSAPP_BRIDGE_TOKEN")
    if not url or not token:
        logger.error("WHATSAPP_BRIDGE_URL / WHATSAPP_BRIDGE_TOKEN are not configured")
        return 1
    bridge = BridgeClient(url, token)

    session = get_session()
    try:
        numeric = ChatMessage.sender_name_raw.op("~")(_NUMERIC_LABEL)
        senders = session.execute(
            select(ChatMessage.wa_sender_jid, ChatMessage.wa_sender_alt_jid, ChatMessage.sender_name_raw,
                   func.count())
            .where(ChatMessage.source == "sync", ChatMessage.is_from_me.is_not(True),
                   ChatMessage.wa_sender_jid.is_not(None), numeric)
            .group_by(ChatMessage.wa_sender_jid, ChatMessage.wa_sender_alt_jid, ChatMessage.sender_name_raw)
        ).all()
        logger.info("%d sender(s) with a number-only label", len(senders))
        named = renamed = 0
        for jid, alt, label, count in senders:
            probe = ChatMessage(wa_sender_jid=jid, wa_sender_alt_jid=alt)
            name, source = bridge_name(bridge, probe, None)
            logger.info("%-16s %-28s x%-4d -> %s", label, jid, count, f"{name} ({source})" if name else "(no name)")
            if not name:
                continue
            named += 1
            if args.apply:
                result = session.execute(
                    update(ChatMessage)
                    .where(ChatMessage.wa_sender_jid == jid, ChatMessage.source == "sync",
                           ChatMessage.is_from_me.is_not(True), ChatMessage.sender_name_raw == label)
                    .values(sender_name_raw=name[:255])
                )
                renamed += result.rowcount or 0
        if args.apply:
            session.commit()
        logger.info("%d of %d sender(s) have a name; %s", named, len(senders),
                    f"{renamed} message(s) renamed" if args.apply else "dry-run, nothing written (use --apply)")
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
