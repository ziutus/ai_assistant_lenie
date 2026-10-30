"""Flask blueprint: browsing imported chat logs (chat_conversations/chat_messages).

Endpoints (x-api-key required via the global before_request):
  GET /chat_conversations/<id>/senders       — aggregated authors and contact status
  POST /chat_conversations/<id>/senders/add_contacts — add up to 50 authors with per-item isolation
  GET /chat_conversations                    — paginated list of imported chats
  GET /chat_conversations/<id>/messages      — paginated message thread (chronological
                                                by default), media served as presigned
                                                MinIO URLs; optional ?sender=/?message_type=/
                                                ?contact_id= filters

  POST /chat_messages/<id>/create_contact    — add the sender of a message to the private contact
                                                book (nickname, phone, WhatsApp picture, provenance)
  POST /chat_messages/<id>/import_url        — add a link written in a message to the library

Messages are populated by imports/whatsapp_chat_import.py and by the live sync
(library/whatsapp_sync_service.py); writes here are explicit owner actions.
"""

import logging
import re
from datetime import datetime
from urllib.parse import urlparse

from flask import Blueprint, abort, g, jsonify, request
from sqlalchemy import func, select

from library import chat_avatars
from library.chat_contact_service import (
    SenderError,
    bridge_name,
    create_contact_from_message,
    sender_nickname,
    sender_phone,
)
from library.db.engine import get_scoped_session
from library.chat_senders_service import list_senders
from library.db.models import ChatConversation, ChatMessage, Contact, Document
from library.whatsapp_parser import is_phone_number

logger = logging.getLogger(__name__)

bp = Blueprint("chat", __name__)

_URL_RE = re.compile(r"https?://[^\s<>\"')\]]+", re.IGNORECASE)
_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "music.youtube.com"}


def _authorized():
    if getattr(g, "auth", None) is None or g.auth.kind not in {"user", "service"}:
        abort(403, "user or service API key required")


def urls_in_text(text: str | None) -> list[str]:
    """http(s) addresses written in a message, in reading order, without repeats."""
    found: dict[str, None] = {}
    for match in _URL_RE.finditer(text or ""):
        url = match.group(0).rstrip(".,;:!?")
        if urlparse(url).netloc:
            found.setdefault(url, None)
    return list(found)


def _url_entries(session, text: str | None) -> list[dict]:
    entries = []
    for url in urls_in_text(text):
        try:
            document = Document.get_by_url(session, url)
        except ValueError:
            continue
        entries.append({"url": url, "document": None if document is None else {
            "id": document.id, "title": document.title, "document_type": document.document_type}})
    return entries


_MENTION_RE = re.compile(r"@(\d{8,20})\b")


def mention_map(session, texts: list[str | None]) -> dict[str, dict]:
    """Who the ``@<number>`` mentions written in these texts stand for.

    WhatsApp stores a mention as the person's LID (or phone number) instead of a name. Anyone who
    wrote in a synced chat is known by that id, so it is looked up among the senders: a linked
    contact wins, else the name the person chose in WhatsApp. Unknown ids are left out."""
    ids = {found for text in texts for found in _MENTION_RE.findall(text or "")}
    if not ids:
        return {}
    keys = {f"{i}@lid": i for i in ids} | {f"{i}@s.whatsapp.net": i for i in ids}
    rows = session.execute(
        select(ChatMessage.wa_sender_jid, ChatMessage.wa_sender_alt_jid, ChatMessage.contact_id,
               ChatMessage.sender_name_raw)
        .where(ChatMessage.wa_sender_jid.in_(keys) | ChatMessage.wa_sender_alt_jid.in_(keys))
        .distinct()
    ).all()
    found: dict[str, dict] = {}
    for jid, alt, contact_id, name in rows:
        for key in (jid, alt):
            mention_id = keys.get(key)
            if mention_id is None:
                continue
            entry = found.setdefault(mention_id, {"contact": None, "name": None})
            if contact_id and entry["contact"] is None:
                entry["contact"] = _contact_summary(session.get(Contact, contact_id))
            if entry["name"] is None and name and not is_phone_number(name) and not name.startswith("WhatsApp "):
                entry["name"] = name
    return {k: v for k, v in found.items() if v["contact"] or v["name"]}


def _avatar_for(storage, message: ChatMessage, memo: dict) -> tuple[str | None, str | None]:
    """(thumbnail link, jid still to fetch): the contact's own thumbnail when the sender is in the
    book, else the cached WhatsApp picture; ``jid`` is set only while nothing has been tried yet."""
    if storage is None or message.is_from_me:
        return None, None
    contact = message.contact
    if contact is not None and contact.photo_thumbnail_storage_key:
        key = contact.photo_thumbnail_storage_key
        if key not in memo:
            memo[key] = storage.presigned_get_url(key)
        return memo[key], None
    jid = chat_avatars.avatar_jid(message)
    if not jid:
        return None, None
    if jid not in memo:
        memo[jid] = chat_avatars.cached(storage, jid)
    url, known = memo[jid]
    return url, (None if known else jid)


def _conversation_dict(conv: ChatConversation) -> dict:
    return {
        "id": conv.id,
        "platform": conv.platform,
        "chat_key": conv.chat_key,
        "display_name": conv.display_name,
        "message_count": conv.message_count,
        "last_imported_at": conv.last_imported_at.isoformat() if conv.last_imported_at else None,
    }


def _contact_summary(contact) -> dict | None:
    if contact is None:
        return None
    display_name = contact.display_label or f"{contact.first_name or ''} {contact.last_name or ''}".strip()
    return {"id": contact.id, "display_name": display_name or None}


@bp.route("/chat_conversations", methods=["GET"])
def list_chat_conversations():
    session = get_scoped_session()
    total = session.execute(select(func.count()).select_from(ChatConversation)).scalar_one()
    offset = request.args.get("offset", default=0, type=int)
    limit = min(request.args.get("limit", default=100, type=int), 500)
    rows = session.execute(
        select(ChatConversation).order_by(ChatConversation.display_name).offset(offset).limit(limit)
    ).scalars().all()
    return jsonify({
        "status": "success",
        "conversations": [_conversation_dict(c) for c in rows],
        "total": total,
        "offset": offset,
        "limit": limit,
    })


@bp.route("/chat_conversations/<int:conversation_id>/messages", methods=["GET"])
def list_chat_messages(conversation_id: int):
    session = get_scoped_session()
    conversation = session.get(ChatConversation, conversation_id)
    if conversation is None:
        return jsonify({"status": "error", "message": "Conversation not found"}), 404

    conditions = [ChatMessage.conversation_id == conversation_id]
    sender = (request.args.get("sender") or "").strip()
    if sender:
        conditions.append(ChatMessage.sender_name_raw == sender)
    contact_id = request.args.get("contact_id", type=int)
    if contact_id is not None:
        conditions.append(ChatMessage.contact_id == contact_id)
    message_type = (request.args.get("message_type") or "").strip()
    if message_type:
        conditions.append(ChatMessage.message_type == message_type)
    date_from = (request.args.get("date_from") or "").strip()
    if date_from:
        try:
            conditions.append(ChatMessage.sent_at >= datetime.strptime(date_from, "%Y-%m-%d"))
        except ValueError:
            pass

    total = session.execute(select(func.count()).select_from(ChatMessage).where(*conditions)).scalar_one()
    offset = request.args.get("offset", default=0, type=int)
    limit = min(request.args.get("limit", default=200, type=int), 1000)
    order = ChatMessage.sent_at.desc() if request.args.get("sort") == "desc" else ChatMessage.sent_at.asc()

    rows = session.execute(
        select(ChatMessage).where(*conditions).order_by(order, ChatMessage.id).offset(offset).limit(limit)
    ).scalars().all()

    # Attachments and sender thumbnails are served as presigned links.
    storage = None
    if any(r.media_storage_key or not r.is_from_me for r in rows):
        from library.config_loader import load_config
        from library.storage import storage_from_config

        storage = storage_from_config(load_config())
    avatar_memo: dict = {}

    messages = [
        {
            "id": m.id,
            "sender_name_raw": m.sender_name_raw,
            "contact": _contact_summary(m.contact),
            "sent_at": m.sent_at.isoformat() if m.sent_at else None,
            "message_type": m.message_type,
            "content": m.content,
            "media_url": storage.presigned_get_url(m.media_storage_key) if (storage and m.media_storage_key) else None,
            "media_original_filename": m.media_original_filename,
            "media_mime_type": m.media_mime_type,
            "media_size_bytes": m.media_size_bytes,
            # live-sync fields; null/"import" for rows from TXT/ZIP imports
            "source": m.source,
            "is_from_me": m.is_from_me,
            "edited_at": m.edited_at.isoformat() if m.edited_at else None,
            "deleted_at": m.deleted_at.isoformat() if m.deleted_at else None,
            "media_status": m.media_status,
            # who sent it, for "add to contacts": only a message of someone not in the book qualifies
            "sender_phone": sender_phone(m) if m.contact_id is None and not m.is_from_me else None,
            "sender_nickname": sender_nickname(m) if m.contact_id is None and not m.is_from_me else None,
            "can_add_contact": m.contact_id is None and not m.is_from_me and m.message_type != "deleted",
            "urls": _url_entries(session, m.content) if m.content and "http" in m.content else [],
            **dict(zip(("avatar_url", "avatar_fetch_jid"), _avatar_for(storage, m, avatar_memo))),
        }
        for m in rows
    ]

    return jsonify({
        "status": "success",
        "conversation": _conversation_dict(conversation),
        "messages": messages,
        "mentions": mention_map(session, [r.content for r in rows]),
        "total": total,
        "offset": offset,
        "limit": limit,
    })


@bp.route("/chat_conversations/<int:conversation_id>/senders", methods=["GET"])
def list_chat_senders(conversation_id: int):
    session = get_scoped_session()
    conversation = session.get(ChatConversation, conversation_id)
    if conversation is None:
        return jsonify({"status": "error", "message": "Conversation not found"}), 404
    status = request.args.get("status")
    if status is not None and status not in {"missing", "in_contacts"}:
        return jsonify({"status": "error", "message": "Invalid status"}), 400
    offset = max(0, request.args.get("offset", default=0, type=int))
    limit = max(1, min(500, request.args.get("limit", default=200, type=int)))
    result = list_senders(session, conversation_id, status=status, q=request.args.get("q", ""),
                          offset=offset, limit=limit)
    return jsonify({"status": "success", "conversation": _conversation_dict(conversation), **result})


@bp.route("/chat_conversations/<int:conversation_id>/senders/add_contacts", methods=["POST"])
def add_chat_sender_contacts(conversation_id: int):
    _authorized()
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"status": "error", "message": "Expected an object"}), 400
    ids = body.get("message_ids")
    if not isinstance(ids, list) or not 1 <= len(ids) <= 50 or any(type(i) is not int for i in ids):
        return jsonify({"status": "error", "message": "Expected 1 to 50 integer message_ids"}), 400
    if ("category_id" in body and type(body["category_id"]) is not int or
            "fetch_photo" in body and type(body["fetch_photo"]) is not bool):
        return jsonify({"status": "error", "message": "Invalid category_id or fetch_photo"}), 400
    session = get_scoped_session()
    if session.get(ChatConversation, conversation_id) is None:
        return jsonify({"status": "error", "message": "Conversation not found"}), 404
    fetch_photo = body.get("fetch_photo", False)
    counts = dict.fromkeys(("created", "linked_existing", "skipped", "error"), 0)
    results = []
    for message_id in ids:
        item = {"message_id": message_id}
        try:
            with session.begin_nested():
                message = session.get(ChatMessage, message_id)
                if message is None or message.conversation_id != conversation_id:
                    item.update(outcome="skipped", reason="not_in_conversation")
                elif message.contact_id is not None:
                    item.update(outcome="skipped", reason="already_in_contacts")
                else:
                    result = create_contact_from_message(
                        session, message, bridge=_bridge() if fetch_photo else None,
                        category_id=body.get("category_id"), fetch_photo=fetch_photo,
                    )
                    item.update(outcome="linked_existing" if result["existing"] else "created",
                                contact_id=result["contact_id"])
        except SenderError:
            item = {"message_id": message_id, "outcome": "error", "reason": "sender_not_eligible"}
        except Exception:
            logger.exception("Creating a contact from chat message %s failed", message_id)
            item = {"message_id": message_id, "outcome": "error", "reason": "could_not_create_contact"}
        counts[item["outcome"]] += 1
        results.append(item)
    session.commit()
    return jsonify({"status": "success", "results": results, "counts": counts})


def _bridge():
    from library.config_loader import load_config
    from library.whatsapp_sync_service import BridgeClient

    config = load_config()
    url, token = config.get("WHATSAPP_BRIDGE_URL"), config.get("WHATSAPP_BRIDGE_TOKEN")
    return BridgeClient(url, token) if url and token else None


MAX_AVATARS_PER_REQUEST = 6


@bp.route("/chat_avatars/fetch", methods=["POST"])
def fetch_chat_avatars():
    """Fetch (and cache) the WhatsApp picture of up to a few senders: body ``{"jids": [...]}``,
    answer ``{"avatars": {jid: url | null}}``. Only ids of people who actually wrote in a chat are
    looked up. A jid the bridge could not answer for (down, busy) is left out so it is retried."""
    _authorized()
    jids = [str(j) for j in ((request.get_json(silent=True) or {}).get("jids") or [])][:MAX_AVATARS_PER_REQUEST]
    session = get_scoped_session()
    known = set(session.scalars(
        select(ChatMessage.wa_sender_jid).where(ChatMessage.wa_sender_jid.in_(jids)).distinct()
    )) | set(session.scalars(
        select(ChatMessage.wa_sender_alt_jid).where(ChatMessage.wa_sender_alt_jid.in_(jids)).distinct()
    ))
    from library.config_loader import load_config
    from library.storage import storage_from_config

    storage, bridge, avatars = storage_from_config(load_config()), _bridge(), {}
    for jid in jids:
        if jid not in known:
            continue
        url, done = chat_avatars.cached(storage, jid)
        if not done and bridge is not None:
            url, done = chat_avatars.fetch_and_cache(storage, bridge, jid)
        if done:
            avatars[jid] = url
    return jsonify({"status": "success", "avatars": avatars})


@bp.route("/chat_messages/<int:message_id>/sender_profile", methods=["GET"])
def chat_message_sender_profile(message_id: int):
    """What WhatsApp knows about the sender, to pre-fill the add-to-contacts form:
    ``nickname`` (null when there is none) and ``source`` (push_name / address_book / message)."""
    _authorized()
    session = get_scoped_session()
    message = session.get(ChatMessage, message_id)
    if message is None:
        return jsonify({"status": "error", "message": "Message not found"}), 404
    nickname, source = sender_nickname(message), "message"
    if nickname is None:
        nickname, source = bridge_name(_bridge(), message, sender_phone(message))
    return jsonify({"status": "success", "nickname": nickname, "source": source if nickname else None,
                    "phone": sender_phone(message)})


@bp.route("/chat_messages/<int:message_id>/create_contact", methods=["POST"])
def create_contact_from_chat_message(message_id: int):
    """Add the sender of this message to the contact book.

    Body (all optional): ``display_label`` (nickname; defaults to the WhatsApp name),
    ``first_name``, ``last_name``, ``category_id``, ``fetch_photo`` (default true) and
    ``existing_contact_id`` (link the sender to a contact already in the book instead)."""
    _authorized()
    session = get_scoped_session()
    message = session.get(ChatMessage, message_id)
    if message is None:
        return jsonify({"status": "error", "message": "Message not found"}), 404
    body = request.get_json(silent=True) or {}
    fetch_photo = bool(body.get("fetch_photo", True))
    try:
        result = create_contact_from_message(
            session, message, bridge=_bridge(),
            display_label=body.get("display_label"), first_name=body.get("first_name"),
            last_name=body.get("last_name"), category_id=body.get("category_id"),
            fetch_photo=fetch_photo, existing_contact_id=body.get("existing_contact_id"),
        )
        session.commit()
    except SenderError:
        session.rollback()
        logger.info("Chat message %s cannot be added to contacts", message_id, exc_info=True)
        return jsonify({"status": "error", "message": "This message's sender cannot be added to contacts"}), 400
    except Exception:
        session.rollback()
        logger.exception("Creating a contact from chat message %s failed", message_id)
        return jsonify({"status": "error", "message": "Could not create the contact"}), 500
    return jsonify({"status": "success", **result}), 201 if result["created"] else 200


@bp.route("/chat_messages/<int:message_id>/import_url", methods=["POST"])
def import_chat_message_url(message_id: int):
    """Add one link written in the message to the library (idempotent).

    YouTube addresses become ``youtube`` documents (transcript fetched by the normal pipeline),
    everything else a ``link`` that is promoted to a webpage right away, like a radar link. The
    discovery source is the chat, so "where did I get this" stays answerable."""
    _authorized()
    session = get_scoped_session()
    message = session.get(ChatMessage, message_id)
    if message is None:
        return jsonify({"status": "error", "message": "Message not found"}), 404
    url = str((request.get_json(silent=True) or {}).get("url") or "").strip()
    if url not in urls_in_text(message.content):
        return jsonify({"status": "error", "message": "url is not written in this message"}), 400

    from library.document_promotion import PromotionError
    from library.document_service import DocumentService

    conversation = session.get(ChatConversation, message.conversation_id)
    parsed = urlparse(url)
    document_type = "youtube" if parsed.netloc.lower() in _YOUTUBE_HOSTS else "link"
    slug = parsed.path.rstrip("/").rsplit("/", 1)[-1].replace("-", " ").replace("_", " ")
    service = DocumentService(session)
    try:
        document, outcome = service.import_document(
            url, document_type, title=slug or parsed.netloc, source=f"WhatsApp: {conversation.display_name}"[:100],
        )
    except ValueError:
        session.rollback()
        logger.info("Chat message %s: link %s was rejected", message_id, parsed.netloc, exc_info=True)
        return jsonify({"status": "error", "message": "This link cannot be added"}), 400
    session.commit()
    created = outcome != "skipped"
    result = {"status": "success", "document_id": document.id, "created": created,
              "document_type": document.document_type}
    if created and document.document_type == "link":
        try:
            promoted = service.promote_link_to_webpage(document.id)
            result.update(document_type=promoted.document_type, processing_job_id=promoted.processing_job_id)
        except PromotionError as exc:
            session.rollback()
            result["promotion_failed"] = exc.reason
    return jsonify(result), 201 if created else 200
