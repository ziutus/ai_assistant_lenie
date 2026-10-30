"""Live WhatsApp sync: the adapter between the receive-only bridge (``whatsapp_bridge/``)
and ``chat_conversations`` / ``chat_messages`` + MinIO.

Flow of one cycle (``sync_once``, run by the ``whatsapp_sync`` worker job):

1. read the bridge status and the chats it has seen (``WhatsappSyncChat`` rows; nothing is
   archived until the owner sets ``enabled``), push the allowlist back to the bridge;
2. per enabled chat, read journal events after ``cursor_seq`` in small batches, apply them
   and advance the cursor **in the same commit** — a message counts as handled only once it
   is stored; only then is it acknowledged to the bridge;
3. download pending attachments separately, a few at a time, with bounded retries.

Identity of a synced message is WhatsApp's own ``(chat JID, message id)`` (unique index);
redelivery, overlapping history batches and restarts therefore cannot duplicate. This module
only reads from the bridge: there is no send path anywhere. Message text is never logged.
"""

import datetime as dt
import hashlib
import logging
import mimetypes
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from zoneinfo import ZoneInfo

import requests
from sqlalchemy import and_, func, select

from library.db.models import ChatConversation, ChatMessage, WhatsappSyncChat, WhatsappSyncState

logger = logging.getLogger(__name__)

EVENT_BATCH = 100
MAX_BATCHES_PER_CHAT = 10  # 1000 events per chat per cycle keeps the NAS calm; the rest waits for the next cycle
MEDIA_PER_CYCLE = 20
MEDIA_CONCURRENCY = 2
MEDIA_MAX_ATTEMPTS = 8
MEDIA_BACKOFF_BASE_SECONDS = 60
MEDIA_BACKOFF_CAP_SECONDS = 6 * 3600
DEFAULT_MEDIA_MAX_BYTES = 50 * 1024 * 1024
DEFAULT_TZ = "Europe/Warsaw"
OWN_SENDER_NAME = "Ja"
LOCK_KEY = 918273646  # pg advisory lock: one sync cycle at a time (scheduled + manual run)

_MIME_EXT_OVERRIDES = {"audio/ogg": ".ogg", "audio/ogg; codecs=opus": ".ogg", "image/webp": ".webp"}


class BridgeError(Exception):
    """Transient bridge failure (unreachable, 5xx, busy): try again later."""


class BridgeAuthError(BridgeError):
    pass


class MediaUnavailable(Exception):
    """The attachment can never be fetched (gone from WhatsApp, too large, no descriptor)."""


class BridgeClient:
    """Thin client for the bridge REST API (see whatsapp_bridge/server.go)."""

    def __init__(self, base_url: str, token: str, timeout: float = 30, http=None):
        self.base = base_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {token}"}
        self.timeout = timeout
        self.http = http or requests.Session()

    def _call(self, method: str, path: str, **kwargs):
        try:
            response = self.http.request(method, self.base + path, headers=self.headers,
                                         timeout=kwargs.pop("timeout", self.timeout), **kwargs)
        except requests.RequestException as exc:
            raise BridgeError(f"bridge unreachable: {type(exc).__name__}") from exc
        if response.status_code == 401:
            raise BridgeAuthError("bridge rejected the token")
        return response

    def _json(self, method: str, path: str, **kwargs) -> dict:
        response = self._call(method, path, **kwargs)
        if response.status_code >= 400:
            raise BridgeError(f"bridge returned HTTP {response.status_code}")
        return response.json()

    def status(self) -> dict:
        return self._json("GET", "/status")

    def chats(self) -> list[dict]:
        return self._json("GET", "/chats")["chats"]

    def put_allowlist(self, jids: list[str]) -> None:
        self._json("PUT", "/allowlist", json={"jids": jids})

    def events(self, chat_jid: str, after: int, limit: int = EVENT_BATCH) -> list[dict]:
        return self._json("GET", "/events", params={"chat": chat_jid, "after": after, "limit": limit})["events"]

    def ack(self, chat_jid: str, upto: int) -> None:
        self._json("POST", "/ack", json={"chat": chat_jid, "upto": upto})

    def media(self, chat_jid: str, wa_id: str) -> bytes:
        response = self._call("GET", "/media", params={"chat": chat_jid, "id": wa_id}, timeout=180)
        if response.status_code in (404, 410, 413):
            raise MediaUnavailable(f"HTTP {response.status_code}")
        if response.status_code >= 400:
            raise BridgeError(f"bridge returned HTTP {response.status_code}")
        return response.content

    def delete_media(self, chat_jid: str, wa_id: str) -> None:
        self._json("DELETE", "/media", params={"chat": chat_jid, "id": wa_id})

    def avatar(self, jid: str) -> tuple[bytes | None, str | None]:
        """Profile picture of one user as (bytes, content type); (None, None) when there is none."""
        response = self._call("GET", "/avatar", params={"jid": jid}, timeout=60)
        if response.status_code == 404:
            return None, None
        if response.status_code >= 400:
            raise BridgeError(f"bridge returned HTTP {response.status_code}")
        return response.content, response.headers.get("Content-Type")

    def qr_png(self) -> bytes | None:
        response = self._call("GET", "/pairing/qr.png")
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise BridgeError(f"bridge returned HTTP {response.status_code}")
        return response.content

    def reset_pairing(self) -> None:
        self._json("POST", "/pairing/reset", timeout=60)


# --- pure helpers ---------------------------------------------------------------------------


def to_local_naive(timestamp: int, tz_name: str = DEFAULT_TZ) -> dt.datetime:
    """Unix seconds -> naive local wall time, the convention of chat_messages.sent_at
    (TXT exports carry naive local times)."""
    return dt.datetime.fromtimestamp(timestamp, ZoneInfo(tz_name)).replace(tzinfo=None)


def phone_from_jid(jid: str | None) -> str | None:
    """'48600600600@s.whatsapp.net' -> '48600600600'; LIDs and groups give None."""
    if not jid or not jid.endswith("@s.whatsapp.net"):
        return None
    digits = re.sub(r"\D", "", jid.split("@", 1)[0].split(":", 1)[0])
    return digits or None


def sync_dedup_hash(chat_jid: str, wa_message_id: str) -> str:
    return hashlib.sha256(f"wa|{chat_jid}|{wa_message_id}".encode()).hexdigest()


def media_storage_key(conversation_id: int, chat_jid: str, wa_message_id: str, mime: str | None) -> str:
    """Object key derived only from ids — never from the sender-supplied file name — and
    deterministic, so a retry overwrites the same object instead of creating another."""
    digest = hashlib.sha256(f"{chat_jid}|{wa_message_id}".encode()).hexdigest()[:40]
    base = (mime or "").split(";")[0].strip().lower()
    ext = _MIME_EXT_OVERRIDES.get(base) or mimetypes.guess_extension(base) or ".bin"
    return f"chat_media/whatsapp/{conversation_id}/{digest}{ext}"


def media_backoff_seconds(attempts: int) -> int:
    return min(MEDIA_BACKOFF_BASE_SECONDS * (2 ** max(attempts - 1, 0)), MEDIA_BACKOFF_CAP_SECONDS)


def sender_label(ev: dict, own_name: str = OWN_SENDER_NAME) -> str:
    if ev.get("is_from_me"):
        return own_name
    name = (ev.get("sender_name") or "").strip()
    if name:
        return name[:255]
    phone = phone_from_jid(ev.get("sender_pn")) or phone_from_jid(ev.get("sender_jid"))
    return f"+{phone}" if phone else f"WhatsApp {str(ev.get('sender_jid') or '?').split('@', 1)[0]}"[:255]


def _minute_bounds(sent_at: dt.datetime) -> tuple[dt.datetime, dt.datetime]:
    start = sent_at.replace(second=0, microsecond=0)
    return start, start + dt.timedelta(minutes=1)


def legacy_key(message_type: str, content: str | None, sent_at: dt.datetime) -> tuple:
    return message_type, content, sent_at.replace(second=0, microsecond=0)


def find_legacy_twin(session, conversation_id: int, ev: dict, sent_at: dt.datetime, contact_id: int | None,
                     batch_key_counts: Counter) -> ChatMessage | None:
    """The single TXT-import row this synced text message certainly corresponds to, else None.

    A TXT export has no message id and minute precision, so identical text in the same minute
    is genuinely ambiguous. Adopt a legacy row only when exactly one unadopted import row has
    this type+text+minute, no other synced row and no other event of the current batch has it
    too, and the resolved contacts (when both known) agree. Everything else stays separate."""
    content = ev.get("text") or None
    if ev["message_type"] != "text" or not content:
        return None
    key = legacy_key(ev["message_type"], content, sent_at)
    if batch_key_counts[key] > 1:
        return None
    start, end = _minute_bounds(sent_at)
    same_minute = and_(
        ChatMessage.conversation_id == conversation_id,
        ChatMessage.message_type == ev["message_type"],
        ChatMessage.content == content,
        ChatMessage.sent_at >= start,
        ChatMessage.sent_at < end,
    )
    already_synced = session.scalar(
        select(func.count()).select_from(ChatMessage).where(same_minute, ChatMessage.wa_message_id.is_not(None))
    )
    if already_synced:
        return None
    legacy = session.scalars(
        select(ChatMessage).where(same_minute, ChatMessage.wa_message_id.is_(None), ChatMessage.source == "import")
    ).all()
    if len(legacy) != 1:
        return None
    if contact_id and legacy[0].contact_id and legacy[0].contact_id != contact_id:
        return None
    return legacy[0]


def sync_twin_exists(session, conversation_id: int, message_type: str, content: str | None,
                     sent_at: dt.datetime) -> bool:
    """Used by the TXT importer: is this exported text message already stored by live sync?
    True only for an unambiguous single synced row in the same minute with the same text."""
    if message_type != "text" or not content:
        return False
    start, end = _minute_bounds(sent_at)
    count = session.scalar(
        select(func.count()).select_from(ChatMessage).where(
            ChatMessage.conversation_id == conversation_id,
            ChatMessage.message_type == "text",
            ChatMessage.content == content,
            ChatMessage.sent_at >= start,
            ChatMessage.sent_at < end,
            ChatMessage.wa_message_id.is_not(None),
        )
    )
    return count == 1


# --- applying events --------------------------------------------------------------------------


class SyncContext:
    def __init__(self, session, storage=None, tz_name: str = DEFAULT_TZ, own_name: str = OWN_SENDER_NAME,
                 phone_index: dict[str, int] | None = None, media_max_bytes: int = DEFAULT_MEDIA_MAX_BYTES,
                 now: dt.datetime | None = None):
        self.session = session
        self.storage = storage
        self.tz_name = tz_name
        self.own_name = own_name
        self.media_max_bytes = media_max_bytes
        self.now = now or dt.datetime.now(ZoneInfo(tz_name)).replace(tzinfo=None)
        if phone_index is None:
            from library.whatsapp_parser import load_contact_phone_index

            phone_index = load_contact_phone_index(session)
        self.phone_index = phone_index

    def contact_for(self, ev: dict) -> int | None:
        if ev.get("is_from_me"):
            return None
        phone = phone_from_jid(ev.get("sender_pn")) or phone_from_jid(ev.get("sender_jid"))
        if not phone:
            return None  # a bare LID is never guessed into a contact
        return self.phone_index.get(phone) or self.phone_index.get(phone[-9:])


def _find_message(session, chat_jid: str, wa_id: str) -> ChatMessage | None:
    return session.scalars(
        select(ChatMessage).where(ChatMessage.wa_chat_jid == chat_jid, ChatMessage.wa_message_id == wa_id)
    ).first()


def _identity(row: ChatMessage, chat_jid: str, ev: dict) -> None:
    row.wa_chat_jid, row.wa_message_id = chat_jid, ev["wa_message_id"]
    row.wa_sender_jid = ev.get("sender_jid") or None
    row.wa_sender_alt_jid = ev.get("sender_alt_jid") or ev.get("sender_pn") or None
    row.is_from_me = bool(ev.get("is_from_me"))


def apply_message(ctx: SyncContext, chat: WhatsappSyncChat, ev: dict, batch_key_counts: Counter) -> str:
    chat_jid = ev["chat_jid"]
    existing = _find_message(ctx.session, chat_jid, ev["wa_message_id"])
    if existing is not None:
        return "duplicate"  # redelivery, overlapping history, or a tombstone/edit that arrived first
    sent_at = to_local_naive(ev["timestamp"], ctx.tz_name)
    contact_id = ctx.contact_for(ev)
    media = ev.get("media")

    twin = find_legacy_twin(ctx.session, chat.conversation_id, ev, sent_at, contact_id, batch_key_counts)
    if twin is not None:
        _identity(twin, chat_jid, ev)
        twin.sent_at = sent_at
        twin.contact_id = twin.contact_id or contact_id
        return "adopted_legacy"
    ambiguous = (
        ev["message_type"] == "text" and ev.get("text")
        and batch_key_counts[legacy_key(ev["message_type"], ev["text"], sent_at)] > 1
    )

    row = ChatMessage(
        conversation_id=chat.conversation_id,
        sender_name_raw=sender_label(ev, ctx.own_name),
        contact_id=contact_id,
        sent_at=sent_at,
        message_type=ev["message_type"],
        content=ev.get("text") or None,
        dedup_hash=sync_dedup_hash(chat_jid, ev["wa_message_id"]),
        source="sync",
        media_attempts=0,
    )
    _identity(row, chat_jid, ev)
    if media is not None:
        row.media_original_filename = media.get("filename") or None
        row.media_mime_type = (media.get("mime") or None)
        row.media_size_bytes = media.get("size") or None
        row.media_status = "pending"
        row.media_next_attempt_at = ctx.now
    ctx.session.add(row)
    ctx.session.flush()
    return "created_ambiguous" if ambiguous else "created"


def apply_edit(ctx: SyncContext, chat: WhatsappSyncChat, ev: dict) -> str:
    edited_at = to_local_naive(ev["timestamp"], ctx.tz_name)
    row = _find_message(ctx.session, ev["chat_jid"], ev["wa_message_id"])
    if row is None:
        # The edit overtook its original: keep the newest text; the original, when it arrives, is a duplicate.
        row = ChatMessage(
            conversation_id=chat.conversation_id, sender_name_raw=sender_label(ev, ctx.own_name),
            contact_id=ctx.contact_for(ev), sent_at=edited_at, message_type="text", content=ev.get("text"),
            dedup_hash=sync_dedup_hash(ev["chat_jid"], ev["wa_message_id"]), source="sync", edited_at=edited_at,
        )
        _identity(row, ev["chat_jid"], ev)
        ctx.session.add(row)
        ctx.session.flush()
        return "edit_created"
    if row.deleted_at is not None:
        return "edit_ignored_deleted"
    if row.edited_at is not None and row.edited_at > edited_at:
        return "edit_ignored_older"
    row.content = ev.get("text") or row.content
    row.edited_at = edited_at
    return "edited"


def apply_revoke(ctx: SyncContext, chat: WhatsappSyncChat, ev: dict) -> str:
    deleted_at = to_local_naive(ev["timestamp"], ctx.tz_name)
    row = _find_message(ctx.session, ev["chat_jid"], ev["wa_message_id"])
    if row is None:
        row = ChatMessage(
            conversation_id=chat.conversation_id, sender_name_raw=sender_label(ev, ctx.own_name),
            contact_id=ctx.contact_for(ev), sent_at=deleted_at, message_type="deleted", content=None,
            dedup_hash=sync_dedup_hash(ev["chat_jid"], ev["wa_message_id"]), source="sync", deleted_at=deleted_at,
        )
        _identity(row, ev["chat_jid"], ev)
        ctx.session.add(row)
        ctx.session.flush()
        return "tombstone_created"
    if row.deleted_at is not None:
        return "duplicate"
    # The earlier content must not stay in the normally readable record.
    key = row.media_storage_key
    row.message_type, row.content, row.deleted_at = "deleted", None, deleted_at
    row.media_storage_key = row.media_original_filename = row.media_mime_type = row.media_size_bytes = None
    row.media_status = row.media_error = row.media_next_attempt_at = None
    if key and ctx.storage is not None:
        try:
            ctx.storage.delete(key)
        except Exception:  # noqa: BLE001 - the record is already scrubbed; the orphan object is not readable via the API
            logger.warning("could not delete media object of a revoked message (chat %s)", chat.id)
    return "revoked"


def apply_events(ctx: SyncContext, chat: WhatsappSyncChat, events: list[dict]) -> Counter:
    stats: Counter = Counter()
    counts: Counter = Counter()
    for ev in events:
        if ev["kind"] == "message" and ev.get("message_type") == "text" and ev.get("text"):
            counts[legacy_key("text", ev["text"], to_local_naive(ev["timestamp"], ctx.tz_name))] += 1
    for ev in events:
        if ev["kind"] == "message":
            outcome = apply_message(ctx, chat, ev, counts)
        elif ev["kind"] == "edit":
            outcome = apply_edit(ctx, chat, ev)
        elif ev["kind"] == "revoke":
            outcome = apply_revoke(ctx, chat, ev)
        else:
            outcome = "unsupported"
        stats[outcome] += 1
    return stats


# --- media ------------------------------------------------------------------------------------


def _fetch_media(bridge: BridgeClient, chat_jid: str, wa_id: str) -> tuple[bytes | None, str | None, bool]:
    """Returns (data, error, permanent). Runs in a worker thread: no database access here."""
    try:
        return bridge.media(chat_jid, wa_id), None, False
    except MediaUnavailable as exc:
        return None, f"unavailable: {exc}", True
    except BridgeError as exc:
        return None, str(exc)[:200], False
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}", False


def process_media(ctx: SyncContext, bridge: BridgeClient, limit: int = MEDIA_PER_CYCLE,
                  concurrency: int = MEDIA_CONCURRENCY) -> Counter:
    """Fetch pending attachments. Every outcome is recorded on the row: downloaded,
    unavailable (permanent), pending with a later retry, or error after MEDIA_MAX_ATTEMPTS."""
    session = ctx.session
    rows = session.scalars(
        select(ChatMessage)
        .where(ChatMessage.media_status == "pending",
               (ChatMessage.media_next_attempt_at.is_(None)) | (ChatMessage.media_next_attempt_at <= ctx.now))
        .order_by(ChatMessage.id).limit(limit)
    ).all()
    stats: Counter = Counter()
    jobs: list[ChatMessage] = []
    for row in rows:
        if row.media_size_bytes and row.media_size_bytes > ctx.media_max_bytes:
            row.media_status, row.media_error = "unavailable", "too_large"
            stats["unavailable"] += 1
        else:
            jobs.append(row)
    session.commit()
    if not jobs:
        return stats
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        results = list(pool.map(lambda r: _fetch_media(bridge, r.wa_chat_jid, r.wa_message_id), jobs))
    for row, (data, error, permanent) in zip(jobs, results):
        if data is not None and len(data) > ctx.media_max_bytes:
            data, error, permanent = None, "unavailable: too_large", True
        if data is not None:
            try:
                key = media_storage_key(row.conversation_id, row.wa_chat_jid, row.wa_message_id, row.media_mime_type)
                ctx.storage.put_bytes(key, data, row.media_mime_type)
            except Exception as exc:  # noqa: BLE001
                data, error, permanent = None, f"storage: {type(exc).__name__}", False
        if data is not None:
            row.media_storage_key, row.media_size_bytes = key, len(data)
            row.media_status, row.media_error, row.media_next_attempt_at = "downloaded", None, None
            stats["downloaded"] += 1
            session.commit()
            try:
                bridge.delete_media(row.wa_chat_jid, row.wa_message_id)
            except BridgeError:
                pass  # the bridge prunes old descriptors itself
            continue
        row.media_attempts += 1
        row.media_error = (error or "failed")[:200]
        if permanent:
            row.media_status, row.media_next_attempt_at = "unavailable", None
            stats["unavailable"] += 1
        elif row.media_attempts >= MEDIA_MAX_ATTEMPTS:
            row.media_status, row.media_next_attempt_at = "error", None
            stats["error"] += 1
        else:
            row.media_next_attempt_at = ctx.now + dt.timedelta(seconds=media_backoff_seconds(row.media_attempts))
            stats["retry_later"] += 1
        session.commit()
    return stats


# --- cycle ------------------------------------------------------------------------------------


def _get_state(session) -> WhatsappSyncState:
    state = session.get(WhatsappSyncState, 1)
    if state is None:
        state = WhatsappSyncState(id=1, connection_state="unknown")
        session.add(state)
        session.flush()
    return state


def _record_error(session, message: str, now: dt.datetime, *, reachable: bool | None = None) -> None:
    session.rollback()
    state = _get_state(session)
    state.last_error, state.last_error_at, state.updated_at = message[:500], now, now
    if reachable is not None:
        state.bridge_reachable = reachable
        state.bridge_checked_at = now
    session.commit()


def refresh_chats(session, bridge: BridgeClient, now: dt.datetime, tz_name: str) -> None:
    known = {c.jid: c for c in session.scalars(select(WhatsappSyncChat))}
    for item in bridge.chats():
        chat = known.get(item["jid"])
        if chat is None:
            chat = WhatsappSyncChat(jid=item["jid"], display_name="", enabled=False)
            session.add(chat)
        if item.get("name"):
            chat.display_name = item["name"][:255]
        chat.is_group = bool(item.get("is_group"))
        chat.buffered_events = int(item.get("buffered_events") or 0)
        if item.get("last_message_ts"):
            chat.last_message_at = to_local_naive(item["last_message_ts"], tz_name)
        chat.updated_at = now
    session.commit()


def ensure_conversation(session, chat: WhatsappSyncChat) -> ChatConversation:
    """The conversation an enabled chat writes into: the one the owner linked, else a new
    one keyed by the WhatsApp JID (a stable id, unlike the display name)."""
    if chat.conversation_id:
        conv = session.get(ChatConversation, chat.conversation_id)
        if conv is not None:
            return conv
    key = f"whatsapp:{chat.jid}"
    conv = session.scalars(select(ChatConversation).where(ChatConversation.chat_key == key)).first()
    if conv is None:
        conv = ChatConversation(platform="whatsapp", chat_key=key, display_name=(chat.display_name or chat.jid)[:255])
        session.add(conv)
        session.flush()
    chat.conversation_id = conv.id
    return conv


def sync_chat(ctx: SyncContext, bridge: BridgeClient, chat: WhatsappSyncChat) -> Counter:
    session = ctx.session
    ensure_conversation(session, chat)
    session.commit()
    total: Counter = Counter()
    for _ in range(MAX_BATCHES_PER_CHAT):
        events = bridge.events(chat.jid, chat.cursor_seq, EVENT_BATCH)
        if not events:
            break
        try:
            stats = apply_events(ctx, chat, events)
            chat.cursor_seq = events[-1]["seq"]
            chat.last_synced_at = ctx.now
            conv = session.get(ChatConversation, chat.conversation_id)
            conv.message_count = session.scalar(
                select(func.count()).select_from(ChatMessage).where(ChatMessage.conversation_id == conv.id)
            )
            newest = session.scalar(
                select(func.max(ChatMessage.sent_at)).where(ChatMessage.conversation_id == conv.id)
            )
            if newest is not None and (conv.last_imported_at is None or newest > conv.last_imported_at):
                conv.last_imported_at = newest
            session.commit()  # cursor and messages become durable together
        except Exception:
            session.rollback()
            raise
        total.update(stats)
        total["events"] += len(events)
        try:
            bridge.ack(chat.jid, chat.cursor_seq)
        except BridgeError:
            pass  # acking only trims the bridge journal; redelivery is harmless
        if len(events) < EVENT_BATCH:
            break
    return total


def _try_lock(session) -> bool:
    if session.get_bind().dialect.name != "postgresql":
        return True
    from sqlalchemy import text

    return bool(session.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": LOCK_KEY}).scalar())


def _unlock(session) -> None:
    if session.get_bind().dialect.name == "postgresql":
        from sqlalchemy import text

        session.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_KEY})


def sync_once(session, bridge: BridgeClient, storage, *, tz_name: str = DEFAULT_TZ, own_name: str = OWN_SENDER_NAME,
              media_max_bytes: int = DEFAULT_MEDIA_MAX_BYTES, now: dt.datetime | None = None,
              phone_index: dict[str, int] | None = None) -> dict:
    now = now or dt.datetime.now(ZoneInfo(tz_name)).replace(tzinfo=None)
    if not _try_lock(session):
        return {"status": "busy"}
    try:
        try:
            status = bridge.status()
        except BridgeError as exc:
            _record_error(session, str(exc), now, reachable=False)
            return {"status": "bridge_unreachable"}
        state = _get_state(session)
        state.bridge_reachable, state.bridge_checked_at = True, now
        state.connection_state = status.get("state") or "unknown"
        state.needs_pairing = bool(status.get("needs_pairing"))
        state.account_jid = status.get("account_jid") or None
        epoch = status.get("epoch")
        reset = bool(epoch and state.bridge_epoch and epoch != state.bridge_epoch)
        if reset:
            # The bridge journal was recreated: its sequence restarted, old cursors would skip messages.
            # Re-reading is safe — identity is unique per WhatsApp message id.
            for chat in session.scalars(select(WhatsappSyncChat)):
                chat.cursor_seq = 0
        state.bridge_epoch = epoch or state.bridge_epoch
        if status.get("last_error"):
            state.last_error, state.last_error_at = str(status["last_error"])[:500], now
        session.commit()

        refresh_chats(session, bridge, now, tz_name)
        enabled = session.scalars(select(WhatsappSyncChat).where(WhatsappSyncChat.enabled.is_(True))).all()
        bridge.put_allowlist([c.jid for c in enabled])

        ctx = SyncContext(session, storage, tz_name, own_name, phone_index=phone_index,
                          media_max_bytes=media_max_bytes, now=now)
        result: dict = {"status": "ok", "chats": len(enabled), "events": 0, "journal_reset": reset}
        error = None
        for chat in enabled:
            try:
                stats = sync_chat(ctx, bridge, chat)
            except BridgeError as exc:
                error = str(exc)
                break
            except Exception as exc:  # noqa: BLE001 - never include message content in the error
                logger.exception("whatsapp sync failed for chat %s", chat.id)
                error = f"chat {chat.id}: {type(exc).__name__}"
                continue
            result["events"] += stats.pop("events", 0)
            for key, value in stats.items():
                result[key] = result.get(key, 0) + value
        if error is None and storage is not None and status.get("state") == "connected":
            media = process_media(ctx, bridge)
            result["media"] = dict(media)
        state = _get_state(session)
        if error:
            _record_error(session, error, now)
            result["status"] = "error"
        else:
            state.last_success_at, state.updated_at = now, now
            if status.get("state") == "connected":
                state.last_error = None
            session.commit()
        return result
    finally:
        _unlock(session)


def execute_whatsapp_sync(session, job) -> dict:
    """Worker entry point. A no-op until the bridge is configured, so the scheduled task can
    ship enabled by default."""
    from library.config_loader import load_config
    from library.storage import storage_from_config

    config = load_config()
    url = config.get("WHATSAPP_BRIDGE_URL")
    token = config.get("WHATSAPP_BRIDGE_TOKEN")
    if not url or not token:
        return {"status": "not_configured"}
    bridge = BridgeClient(url, token)
    return sync_once(
        session, bridge, storage_from_config(config),
        tz_name=config.get("WHATSAPP_SYNC_TIMEZONE") or DEFAULT_TZ,
        own_name=config.get("WHATSAPP_OWN_SENDER_NAME") or OWN_SENDER_NAME,
        media_max_bytes=int(config.get("WHATSAPP_MEDIA_MAX_BYTES") or DEFAULT_MEDIA_MAX_BYTES),
    )
