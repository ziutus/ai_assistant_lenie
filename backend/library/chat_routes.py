"""Flask blueprint: browsing imported chat logs (chat_conversations/chat_messages).

Endpoints (x-api-key required via the global before_request):
  GET /chat_conversations                    — paginated list of imported chats
  GET /chat_conversations/<id>/messages      — paginated message thread (chronological
                                                by default), media served as presigned
                                                MinIO URLs; optional ?sender=/?message_type=/
                                                ?contact_id= filters

Read-only — chat_conversations/chat_messages are populated exclusively by
imports/whatsapp_chat_import.py; there is no write path here.
"""

import logging
from datetime import datetime

from flask import Blueprint, jsonify, request
from sqlalchemy import func, select

from library.db.engine import get_scoped_session
from library.db.models import ChatConversation, ChatMessage

logger = logging.getLogger(__name__)

bp = Blueprint("chat", __name__)


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

    # Presigning is a network call to MinIO — only pay for it when this page
    # of messages actually has attachments.
    storage = None
    if any(r.media_storage_key for r in rows):
        from library.config_loader import load_config
        from library.storage import storage_from_config

        storage = storage_from_config(load_config())

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
        }
        for m in rows
    ]

    return jsonify({
        "status": "success",
        "conversation": _conversation_dict(conversation),
        "messages": messages,
        "total": total,
        "offset": offset,
        "limit": limit,
    })
