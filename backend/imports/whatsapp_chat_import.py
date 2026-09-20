#!/usr/bin/env python3
"""Full WhatsApp chat log import: every message from every participant, plus
attachments, into chat_conversations/chat_messages.

Distinct from imports/whatsapp_neighbor_profiles.py, which reads the same
export format but writes LLM-distilled facts about each sender onto
Contact.whatsapp_profile and never stores raw message text. This script does
the opposite: it stores the raw log (message-for-message, all participants)
and never runs an LLM. The two are independent and can both be run against
the same export.

Privacy note: because this stores every participant's actual message text
(not just the account owner's), it should only be pointed at chats the
account owner has the right to archive in full (e.g. a group they're a
member of), not at content belonging to someone else.

Input format: WhatsApp's own "Export chat" — either the media-included
export (a .zip containing one .txt plus every attachment file, named
exactly as referenced in the .txt as "<filename> (załączony plik)") or the
text-only export (a bare .txt, no attachment bytes available). Pass either
to --export; a .zip is detected automatically via its file signature. Some
attachments have their bytes intentionally excluded by WhatsApp itself even
inside a media export (e.g. the per-file/total export size limit was hit) —
these still show up as a bare "<Pominięto multimedia>" line followed by the
filename with no timestamp; they're recorded with `media_original_filename`
set but `media_storage_key` left NULL (nothing to upload).

Idempotent re-import: WhatsApp exports carry no stable per-message id, so a
message's identity for dedup purposes is `sha256(chat_key|sender_name_raw|
sent_at|content-or-filename)` (`chat_messages.dedup_hash`, unique). Re-running
against a newer export of the same --chat-key only inserts messages whose
hash isn't already stored — safe to re-run on every fresh export. A known
limitation: if a message was first imported with --skip-media, a later
re-import won't retroactively upload its attachment (the row's dedup_hash is
unchanged, so it's treated as already-imported) — delete the row first if a
media backfill is needed for it.

contact_id is resolve-only (library.whatsapp_parser.find_contact) — unlike
whatsapp_neighbor_profiles.py, this script never creates a Contact for a
sender it doesn't already recognize (by phone or by name); a full multi-
participant message log is not a reason to spawn a Contact row for every
group member it happens to see.

Usage:
    cd backend
    python imports/whatsapp_chat_import.py --export "chat.zip" --chat-key "tuwima-gardens/czat-ogolny" --chat-name "Tuwima Gardens - Czat ogólny"
    python imports/whatsapp_chat_import.py --export "chat.zip" --chat-key "..." --chat-name "..." --apply
    python imports/whatsapp_chat_import.py --export "chat.zip" --chat-key "..." --chat-name "..." --apply --skip-media
    python imports/whatsapp_chat_import.py --export "chat.zip" --chat-key "..." --chat-name "..." --apply --limit 50 -v
"""

import argparse
import hashlib
import logging
import mimetypes
import os
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from library.whatsapp_parser import (  # noqa: E402
    find_contact,
    guess_media_type,
    is_deleted,
    is_phone_number,
    load_contact_name_index,
    load_contact_phone_index,
    message_datetime,
    parse_attachment,
    parse_export,
)

logger = logging.getLogger("whatsapp_chat_import")

DEFAULT_CONTENT_TYPE = "application/octet-stream"
# Extensions mimetypes' stdlib table doesn't know (or gets wrong for this use).
_MIME_OVERRIDES = {".opus": "audio/ogg"}


class ChatExport:
    """Uniform access to a WhatsApp export's parsed .txt path and, when the
    export is a media .zip, its attachment bytes by filename."""

    def __init__(self, export_path: str):
        self.export_path = export_path
        self._zip = None
        self._zip_names: set[str] = set()
        self.txt_path = export_path

        if zipfile.is_zipfile(export_path):
            self._zip = zipfile.ZipFile(export_path)
            self._zip_names = set(self._zip.namelist())
            txt_names = [n for n in self._zip_names if n.lower().endswith(".txt")]
            if not txt_names:
                raise ValueError(f"Nie znaleziono pliku .txt w archiwum {export_path}")
            data = self._zip.read(txt_names[0]).decode("utf-8", errors="replace")
            fd, self.txt_path = tempfile.mkstemp(suffix=".txt")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(data)

    @property
    def has_media(self) -> bool:
        return self._zip is not None

    def read_media(self, filename: str) -> bytes | None:
        if self._zip is None or filename not in self._zip_names:
            return None
        return self._zip.read(filename)

    def close(self):
        if self._zip is not None:
            self._zip.close()
        if self.txt_path != self.export_path and os.path.exists(self.txt_path):
            os.remove(self.txt_path)


def guess_mime_type(filename: str) -> str:
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in _MIME_OVERRIDES:
        return _MIME_OVERRIDES[ext]
    return mimetypes.guess_type(filename)[0] or DEFAULT_CONTENT_TYPE


def classify_message(m: dict) -> dict:
    """Returns {message_type, content, attachment_filename, embedded}."""
    content = m["content"]
    if is_deleted(content):
        return {"message_type": "deleted", "content": None, "attachment_filename": None, "embedded": False}
    attachment = parse_attachment(content)
    if attachment:
        filename, embedded = attachment
        return {
            "message_type": guess_media_type(filename), "content": None,
            "attachment_filename": filename, "embedded": embedded,
        }
    return {"message_type": "text", "content": content, "attachment_filename": None, "embedded": False}


def compute_dedup_hash(chat_key: str, sender: str, sent_at, payload: str) -> str:
    raw = f"{chat_key}|{sender}|{sent_at.isoformat() if sent_at else ''}|{payload}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--export", required=True,
                        help="Ścieżka do eksportu czatu WhatsApp (.zip z multimediami lub sam .txt)")
    parser.add_argument("--chat-key", required=True,
                        help="Stabilny identyfikator rozmowy — ten sam przy kolejnych eksportach tej samej grupy")
    parser.add_argument("--chat-name", required=True,
                        help="Wyświetlana nazwa rozmowy (chat_conversations.display_name)")
    parser.add_argument("--platform", default="whatsapp")
    parser.add_argument("--limit", type=int, default=None, help="Maks. liczba wiadomości do przetworzenia w tym uruchomieniu (testy)")
    parser.add_argument("--force", action="store_true", help="Zignoruj watermark (last_imported_at) i przetwórz całą historię od nowa")
    parser.add_argument("--skip-media", action="store_true", help="Nie wgrywaj załączników do MinIO, tylko log tekstowy")
    parser.add_argument("--apply", action="store_true", help="Zapisz do bazy (domyślnie: tylko podgląd/statystyki)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")

    export = ChatExport(args.export)
    try:
        messages = parse_export(export.txt_path)
        logger.info("Sparsowano %d wiadomości z eksportu.", len(messages))
        if not export.has_media:
            logger.warning("Eksport bez multimediów (sam .txt) — załączniki zostaną zapisane tylko jako nazwa pliku, bez wgrywania.")

        session = None
        conversation = None
        phone_index: dict[str, int] = {}
        name_index: dict[str, int] = {}
        existing_hashes: set[str] = set()
        storage = None
        watermark = None

        if args.apply:
            from sqlalchemy import func, select

            from library.config_loader import load_config
            from library.db.engine import get_session
            from library.db.models import ChatConversation, ChatMessage
            from library.storage import storage_from_config

            session = get_session()
            conversation = session.execute(
                select(ChatConversation).where(ChatConversation.chat_key == args.chat_key)
            ).scalars().first()
            if conversation is None:
                conversation = ChatConversation(platform=args.platform, chat_key=args.chat_key, display_name=args.chat_name)
                session.add(conversation)
                session.flush()
                logger.info("Utworzono nową rozmowę #%d: %s", conversation.id, args.chat_key)
            else:
                if conversation.display_name != args.chat_name:
                    conversation.display_name = args.chat_name
                if not args.force:
                    watermark = conversation.last_imported_at

            existing_hashes = set(session.scalars(
                select(ChatMessage.dedup_hash).where(ChatMessage.conversation_id == conversation.id)
            ))
            phone_index = load_contact_phone_index(session)
            name_index = load_contact_name_index(session)
            if not args.skip_media:
                storage = storage_from_config(load_config())

        stats: dict[str, int] = {}
        media_uploaded = media_excluded_from_export = media_missing_bytes = 0
        created_count = duplicate_count = skipped_watermark = 0
        processed = 0
        last_seen_sent_at = None

        for m in messages:
            sent_at = message_datetime(m)
            if watermark is not None and sent_at is not None and sent_at <= watermark:
                skipped_watermark += 1
                continue
            if args.limit and processed >= args.limit:
                break
            processed += 1
            last_seen_sent_at = sent_at or last_seen_sent_at

            info = classify_message(m)
            message_type = info["message_type"]
            content = info["content"]
            attachment_filename = info["attachment_filename"]
            stats[message_type] = stats.get(message_type, 0) + 1

            media_storage_key = media_mime_type = media_original_filename = None
            media_size_bytes = None
            if attachment_filename:
                media_original_filename = attachment_filename
                media_mime_type = guess_mime_type(attachment_filename)
                if not info["embedded"]:
                    media_excluded_from_export += 1
                elif not args.skip_media:
                    data = export.read_media(attachment_filename)
                    if data is None:
                        media_missing_bytes += 1
                        logger.debug("Załącznik w eksporcie nieznaleziony w archiwum: %s", attachment_filename)
                    else:
                        media_size_bytes = len(data)
                        media_uploaded += 1
                        if args.apply:
                            digest = hashlib.sha256(data).hexdigest()[:16]
                            safe_name = os.path.basename(attachment_filename)
                            media_storage_key = f"chat_media/{args.chat_key}/{digest}_{safe_name}"
                            storage.put_bytes(media_storage_key, data, media_mime_type)

            dedup_payload = content if content is not None else (media_original_filename or message_type)
            dedup_hash = compute_dedup_hash(args.chat_key, m["sender"], sent_at, dedup_payload)

            if not args.apply:
                continue

            if dedup_hash in existing_hashes:
                duplicate_count += 1
                continue
            existing_hashes.add(dedup_hash)

            phone = m["sender"] if is_phone_number(m["sender"]) else None
            contact_id = find_contact(m["sender"], phone, phone_index, name_index)

            session.add(ChatMessage(
                conversation_id=conversation.id,
                sender_name_raw=m["sender"],
                contact_id=contact_id,
                sent_at=sent_at,
                message_type=message_type,
                content=content,
                media_storage_key=media_storage_key,
                media_original_filename=media_original_filename,
                media_mime_type=media_mime_type if media_original_filename else None,
                media_size_bytes=media_size_bytes,
                dedup_hash=dedup_hash,
            ))
            created_count += 1

        conversation_summary = None
        if args.apply:
            session.commit()
            total = session.execute(
                select(func.count()).select_from(ChatMessage).where(ChatMessage.conversation_id == conversation.id)
            ).scalar_one()
            conversation.message_count = total
            if last_seen_sent_at is not None and (conversation.last_imported_at is None
                                                    or last_seen_sent_at > conversation.last_imported_at):
                conversation.last_imported_at = last_seen_sent_at
            session.commit()
            # Capture display values before closing the session — attribute access on a
            # detached instance after commit() (expire_on_commit=True) tries to refresh
            # from the DB and raises DetachedInstanceError once the session is closed.
            conversation_summary = (conversation.id, conversation.display_name,
                                     conversation.message_count, conversation.last_imported_at)
            session.close()

        print()
        print(f"Wiadomości w eksporcie: {len(messages)}")
        if watermark is not None:
            print(f"Pominięto (przed watermarkiem {watermark}): {skipped_watermark}")
        print(f"Przetworzonych w tym uruchomieniu: {processed}")
        print(f"Rozkład typów: {stats}")
        print(f"Załączniki: wgranych/do wgrania {media_uploaded}, media pominięte przez WhatsApp w eksporcie {media_excluded_from_export}, "
              f"zapowiedziane w tekście ale brak w archiwum {media_missing_bytes}")
        if args.apply:
            conv_id, conv_name, conv_count, conv_watermark = conversation_summary
            print(f"Utworzono nowych wierszy chat_messages: {created_count}")
            print(f"Pominięto duplikatów (dedup_hash już w bazie): {duplicate_count}")
            print(f"Rozmowa #{conv_id} „{conv_name}”: {conv_count} wiadomości łącznie, watermark: {conv_watermark}")
        else:
            print("[DRY-RUN] Nic nie zapisano — użyj --apply, by zaimportować.")
    finally:
        export.close()


if __name__ == "__main__":
    main()
