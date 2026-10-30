"""Flask blueprint: status and chat selection for the live WhatsApp sync.

  GET   /whatsapp_sync/status            — bridge connection, last import, pending attachments, last error
  GET   /whatsapp_sync/chats             — chats the bridge has seen, with the owner's selection
  PATCH /whatsapp_sync/chats/<id>        — {enabled?, conversation_id?}; nothing is archived until enabled
  POST  /whatsapp_sync/run               — queue a sync cycle now
  GET   /whatsapp_sync/pairing/qr.png    — QR code for (re)pairing, proxied from the bridge
  POST  /whatsapp_sync/pairing/reset     — unlink and start a fresh pairing

Responses never contain message text. Pairing and selection need a user or service key.
"""

import logging

from flask import Blueprint, Response, abort, g, jsonify, request
from sqlalchemy import func, select

from library.db.engine import get_scoped_session
from library.db.models import ChatConversation, ChatMessage, WhatsappSyncChat, WhatsappSyncState

logger = logging.getLogger(__name__)

bp = Blueprint("whatsapp_sync", __name__)


def _authorized():
    if getattr(g, "auth", None) is None or g.auth.kind not in {"user", "service"}:
        abort(403, "user or service API key required")


def _iso(value):
    return value.isoformat() if value else None


def _chat_dict(chat: WhatsappSyncChat) -> dict:
    return {
        "id": chat.id,
        "jid": chat.jid,
        "display_name": chat.display_name,
        "is_group": chat.is_group,
        "enabled": chat.enabled,
        "conversation_id": chat.conversation_id,
        "buffered_events": chat.buffered_events,
        "last_message_at": _iso(chat.last_message_at),
        "last_synced_at": _iso(chat.last_synced_at),
    }


def _bridge():
    from library.config_loader import load_config
    from library.whatsapp_sync_service import BridgeClient

    config = load_config()
    url, token = config.get("WHATSAPP_BRIDGE_URL"), config.get("WHATSAPP_BRIDGE_TOKEN")
    if not url or not token:
        return None
    return BridgeClient(url, token)


@bp.route("/whatsapp_sync/status", methods=["GET"])
def whatsapp_sync_status():
    _authorized()
    session = get_scoped_session()
    state = session.get(WhatsappSyncState, 1)
    count_media = lambda status: session.scalar(  # noqa: E731
        select(func.count()).select_from(ChatMessage).where(ChatMessage.media_status == status)
    )
    return jsonify({
        "status": "success",
        "configured": _bridge() is not None,
        "connection_state": state.connection_state if state else "unknown",
        "bridge_reachable": bool(state and state.bridge_reachable),
        "needs_pairing": bool(state and state.needs_pairing),
        "bridge_checked_at": _iso(state.bridge_checked_at) if state else None,
        "last_success_at": _iso(state.last_success_at) if state else None,
        "last_error": state.last_error if state else None,
        "last_error_at": _iso(state.last_error_at) if state else None,
        "enabled_chats": session.scalar(
            select(func.count()).select_from(WhatsappSyncChat).where(WhatsappSyncChat.enabled.is_(True))
        ),
        "media": {
            "pending": count_media("pending"),
            "unavailable": count_media("unavailable"),
            "error": count_media("error"),
        },
        "note": "WhatsApp provides only part of the history and older media; this is not a complete archive.",
    })


@bp.route("/whatsapp_sync/chats", methods=["GET"])
def whatsapp_sync_chats():
    _authorized()
    session = get_scoped_session()
    rows = session.scalars(
        select(WhatsappSyncChat).order_by(WhatsappSyncChat.enabled.desc(), WhatsappSyncChat.last_message_at.desc())
    ).all()
    return jsonify({"status": "success", "chats": [_chat_dict(c) for c in rows]})


@bp.route("/whatsapp_sync/chats/<int:chat_id>", methods=["PATCH"])
def whatsapp_sync_update_chat(chat_id: int):
    _authorized()
    session = get_scoped_session()
    chat = session.get(WhatsappSyncChat, chat_id)
    if chat is None:
        return jsonify({"status": "error", "message": "Chat not found"}), 404
    body = request.get_json(silent=True) or {}
    if "conversation_id" in body:
        conversation_id = body["conversation_id"]
        if conversation_id is not None:
            if not isinstance(conversation_id, int) or isinstance(conversation_id, bool) \
                    or session.get(ChatConversation, conversation_id) is None:
                return jsonify({"status": "error", "message": "Unknown conversation_id"}), 400
        chat.conversation_id = conversation_id
    if "enabled" in body:
        if not isinstance(body["enabled"], bool):
            return jsonify({"status": "error", "message": "enabled must be a boolean"}), 400
        chat.enabled = body["enabled"]
    session.commit()
    return jsonify({"status": "success", "chat": _chat_dict(chat)})


@bp.route("/whatsapp_sync/run", methods=["POST"])
def whatsapp_sync_run():
    _authorized()
    from library.job_queue import enqueue

    job = enqueue(get_scoped_session(), "whatsapp_sync")
    return jsonify({"status": "success", "job_id": str(job.id)}), 202


@bp.route("/whatsapp_sync/pairing/qr.png", methods=["GET"])
def whatsapp_sync_qr():
    _authorized()
    from library.whatsapp_sync_service import BridgeError

    bridge = _bridge()
    if bridge is None:
        return jsonify({"status": "error", "message": "Bridge is not configured"}), 409
    try:
        png = bridge.qr_png()
    except BridgeError:
        return jsonify({"status": "error", "message": "Bridge unavailable"}), 503
    if png is None:
        return jsonify({"status": "error", "message": "No pairing in progress"}), 404
    return Response(png, mimetype="image/png", headers={"Cache-Control": "no-store"})


@bp.route("/whatsapp_sync/pairing/reset", methods=["POST"])
def whatsapp_sync_reset_pairing():
    _authorized()
    from library.whatsapp_sync_service import BridgeError

    bridge = _bridge()
    if bridge is None:
        return jsonify({"status": "error", "message": "Bridge is not configured"}), 409
    try:
        bridge.reset_pairing()
    except BridgeError:
        return jsonify({"status": "error", "message": "Bridge unavailable"}), 503
    return jsonify({"status": "success"}), 202
