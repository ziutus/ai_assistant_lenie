"""Turn the sender of a chat message into a private-contact-book entry.

The live WhatsApp sync resolves a sender to a contact only through a phone number that is
already in the book; everybody else stays a bare ``+48…`` / push-name label. Here the owner
adds such a person on purpose: the contact gets the WhatsApp nickname (``display_label``),
the phone number, the profile picture (fetched through the bridge, best effort) and the
provenance — a contact group named after the chat and a note saying where the two met.
All other still-unresolved messages of the same sender are attached to the new contact.
"""

import datetime as dt
import logging
import re

from sqlalchemy import and_, or_, select, update

from library.contact_change_log import record_contact_change
from library.db.models import ChatConversation, ChatMessage, Contact, ContactCategory, ContactGroup
from library.whatsapp_parser import is_phone_number, load_contact_phone_index, split_display_name
from library.whatsapp_sync_service import BridgeError, phone_from_jid

logger = logging.getLogger(__name__)

_IMAGE_EXTENSIONS = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}


class SenderError(Exception):
    """The message cannot be turned into a contact (own message, deleted, no sender)."""


def sender_phone(message: ChatMessage) -> str | None:
    """Digits of the sender's phone number: a synced message knows it from its JIDs, a TXT
    import only when the label itself is a phone number."""
    for jid in (message.wa_sender_alt_jid, message.wa_sender_jid):
        phone = phone_from_jid(jid)
        if phone:
            return phone
    if is_phone_number(message.sender_name_raw):
        digits = re.sub(r"\D", "", message.sender_name_raw)
        return digits or None
    return None


def sender_nickname(message: ChatMessage) -> str | None:
    """The name the sender chose for themselves (WhatsApp push name); None for a bare number."""
    name = (message.sender_name_raw or "").strip()
    return None if not name or is_phone_number(name) or name.startswith("WhatsApp ") else name


def _sender_filter(message: ChatMessage):
    base = [ChatMessage.contact_id.is_(None), ChatMessage.is_from_me.is_not(True)]
    if message.wa_sender_jid:
        return and_(*base, or_(ChatMessage.wa_sender_jid == message.wa_sender_jid,
                               and_(ChatMessage.conversation_id == message.conversation_id,
                                    ChatMessage.sender_name_raw == message.sender_name_raw,
                                    ChatMessage.wa_sender_jid.is_(None))))
    return and_(*base, ChatMessage.conversation_id == message.conversation_id,
                ChatMessage.sender_name_raw == message.sender_name_raw)


def link_sender_messages(session, message: ChatMessage, contact_id: int) -> int:
    result = session.execute(update(ChatMessage).where(_sender_filter(message)).values(contact_id=contact_id))
    return result.rowcount or 0


def _channel_group(session, conversation: ChatConversation) -> ContactGroup:
    name = f"WhatsApp: {conversation.display_name}"[:100]
    group = session.scalars(select(ContactGroup).where(ContactGroup.name == name)).first()
    if group is None:
        group = ContactGroup(name=name, description="Osoby poznane z tego kanału WhatsApp")
        session.add(group)
        session.flush()
    return group


def _default_category_id(session) -> int:
    category_id = session.scalar(select(ContactCategory.id).order_by(ContactCategory.id).limit(1))
    if category_id is None:
        raise SenderError("no contact category exists")
    return category_id


def _fetch_avatar(bridge, message: ChatMessage, phone: str | None) -> tuple[bytes | None, str | None, str]:
    """(bytes, extension, status) — status: stored | none | unavailable."""
    jid = f"{phone}@s.whatsapp.net" if phone else message.wa_sender_jid
    if bridge is None or not jid:
        return None, None, "unavailable"
    try:
        data, content_type = bridge.avatar(jid)
    except BridgeError:
        return None, None, "unavailable"
    if not data:
        return None, None, "none"
    extension = _IMAGE_EXTENSIONS.get((content_type or "").split(";")[0].strip().lower())
    return (data, extension, "stored") if extension else (None, None, "none")


def _store_photo(session, contact: Contact, data: bytes, extension: str) -> None:
    from library.contact_photo_thumbnails import _photo_thumbnail_storage_key, generate_photo_thumbnail
    from library.contact_photos import ensure_photo_link
    from library.contact_routes import _photo_storage_key
    from library.config_loader import load_config
    from library.db.models import ContactPhoto
    from library.storage import storage_from_config

    storage = storage_from_config(load_config())
    key = _photo_storage_key(contact.uuid, extension)
    storage.put_bytes(key, data, content_type={v: k for k, v in _IMAGE_EXTENSIONS.items()}[extension])
    thumbnail_key = None
    try:
        thumbnail_key = _photo_thumbnail_storage_key(contact.uuid, key)
        storage.put_bytes(thumbnail_key, generate_photo_thumbnail(data), content_type="image/jpeg")
    except Exception:  # noqa: BLE001 - the photo itself is stored; a missing thumbnail can be regenerated
        thumbnail_key = None
        logger.warning("Could not store a thumbnail of the WhatsApp picture for contact %s", contact.id, exc_info=True)
    session.add(ContactPhoto(storage_key=key, user_description_revision=0, ai_descriptions={}))
    session.flush()
    contact.photo_storage_key = key
    contact.photo_thumbnail_storage_key = thumbnail_key
    ensure_photo_link(session, contact.id, key)


def create_contact_from_message(session, message: ChatMessage, *, bridge=None, display_label: str | None = None,
                                first_name: str | None = None, last_name: str | None = None,
                                category_id: int | None = None, fetch_photo: bool = True,
                                existing_contact_id: int | None = None) -> dict:
    """Create (or, with ``existing_contact_id``, only link) the contact for this message's sender.

    A phone number that is already in the book is never duplicated: the existing contact is
    linked instead and reported as ``existing``. The caller commits."""
    if message.is_from_me:
        raise SenderError("own messages have no sender to add")
    if message.message_type == "deleted" and not message.sender_name_raw:
        raise SenderError("the message has no sender")
    conversation = session.get(ChatConversation, message.conversation_id)
    phone = sender_phone(message)
    nickname = sender_nickname(message)

    contact, created = None, False
    if existing_contact_id:
        contact = session.get(Contact, existing_contact_id)
        if contact is None:
            raise SenderError("contact not found")
    elif phone:
        digits = load_contact_phone_index(session)
        found = digits.get(phone) or digits.get(phone[-9:])
        contact = session.get(Contact, found) if found else None
    if contact is None:
        label = (display_label or nickname or "").strip() or None
        first, last = (first_name or "").strip() or None, (last_name or "").strip() or None
        if not (first or last) and not label:
            first, last = split_display_name(message.sender_name_raw)  # a bare number is kept whole as last_name
        contact = Contact(
            category_id=category_id or _default_category_id(session), first_name=first, last_name=last,
            display_label=label[:200] if label else None, phone_number=f"+{phone}" if phone else None,
        )
        session.add(contact)
        session.flush()
        created = True

    note = f"Poznany(-a) z kanału WhatsApp „{conversation.display_name}”."
    if nickname and nickname != contact.display_label:
        note += f" Pseudonim w WhatsApp: {nickname}."
    if note not in (contact.notes or ""):
        contact.notes = f"{contact.notes}\n{note}" if contact.notes else note
    group = _channel_group(session, conversation)
    if group not in contact.groups:
        contact.groups.append(group)
    if phone and not contact.phone_number:
        contact.phone_number = f"+{phone}"

    photo = "skipped"
    if fetch_photo and not contact.photo_storage_key:
        data, extension, photo = _fetch_avatar(bridge, message, phone)
        if data and extension:
            try:
                _store_photo(session, contact, data, extension)
            except Exception:  # noqa: BLE001 - the contact is still worth keeping without the picture
                logger.warning("Storing the WhatsApp picture failed for contact %s", contact.id, exc_info=True)
                photo = "unavailable"
    contact.updated_at = dt.datetime.now()
    linked = link_sender_messages(session, message, contact.id)
    # the message itself may already be attached to this very contact id by a previous run
    message.contact_id = contact.id
    record_contact_change(
        session, contact, "other", changed_fields=["created_from_whatsapp" if created else "linked_to_whatsapp"],
        note=f"Kanał WhatsApp: {conversation.display_name}",
    )
    return {"contact_id": contact.id, "created": created, "existing": not created, "photo": photo,
            "linked_messages": linked, "group": group.name}
