"""Profile-picture thumbnails of chat senders, cached in object storage.

A sender who is in the contact book shows the contact's own thumbnail. Anyone else gets the
WhatsApp profile picture, fetched once through the bridge (``GET /avatar``), reduced to a small
JPEG and kept under ``chat_avatars/whatsapp/<hash of the sender jid>``. "This person has no (or
hides their) picture" is cached too, as a ``.none`` marker, so the bridge is not asked again on
every page view. A bridge error caches nothing: the picture is simply tried again later.
"""

import hashlib
import logging

from library.contact_photo_thumbnails import generate_photo_thumbnail
from library.db.models import ChatMessage
from library.whatsapp_sync_service import BridgeError

logger = logging.getLogger(__name__)

_PREFIX = "chat_avatars/whatsapp/"


def _digest(jid: str) -> str:
    return hashlib.sha256(jid.encode()).hexdigest()[:32]


def photo_key(jid: str) -> str:
    return f"{_PREFIX}{_digest(jid)}.jpg"


def none_key(jid: str) -> str:
    return f"{_PREFIX}{_digest(jid)}.none"


def avatar_jid(message: ChatMessage) -> str | None:
    """The id to ask WhatsApp for a picture and to cache under: the phone-number JID when known,
    else whatever the sender is known by."""
    for jid in (message.wa_sender_alt_jid, message.wa_sender_jid):
        if jid and jid.endswith("@s.whatsapp.net"):
            return jid
    return message.wa_sender_jid or None


def cached(storage, jid: str) -> tuple[str | None, bool]:
    """(url, known): the cached picture's link; ``known`` is False when nothing has been tried yet."""
    if storage.exists(photo_key(jid)):
        return storage.presigned_get_url(photo_key(jid)), True
    if storage.exists(none_key(jid)):
        return None, True
    return None, False


def fetch_and_cache(storage, bridge, jid: str) -> tuple[str | None, bool]:
    """Ask the bridge for the picture of ``jid`` and cache the result; same return as ``cached``."""
    try:
        data, _content_type = bridge.avatar(jid)
    except BridgeError:
        return None, False
    if data:
        try:
            storage.put_bytes(photo_key(jid), generate_photo_thumbnail(data), content_type="image/jpeg")
            return storage.presigned_get_url(photo_key(jid)), True
        except Exception:  # noqa: BLE001 - an unreadable image is as good as none
            logger.warning("Could not store the WhatsApp picture thumbnail", exc_info=True)
    storage.put_bytes(none_key(jid), b"1", content_type="text/plain")
    return None, True
