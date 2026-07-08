"""Flask blueprint: API-key identity and management (Etap 8).

Endpoints (x-api-key required via the global before_request; management
endpoints additionally require a SERVICE key — user keys get 403):
  GET    /whoami            — identity carried by the presented key
  GET    /api_keys          — [service] list keys (no hashes, prefix only)
  POST   /api_keys          — [service] create key {kind, name, user_id?};
                              returns the plaintext ONCE
  DELETE /api_keys/<id>     — [service] deactivate (active=false)
"""

import logging

from flask import Blueprint, abort, g, jsonify, request
from sqlalchemy import select

from library.auth import create_api_key, deactivate_api_key
from library.db.engine import get_scoped_session
from library.db.models import ApiKey, User

logger = logging.getLogger(__name__)

bp = Blueprint("api_keys", __name__)


def _require_auth():
    auth = getattr(g, "auth", None)
    if auth is None:
        abort(401, "request is not authenticated")
    return auth


def _require_service():
    auth = _require_auth()
    if auth.kind != "service":
        abort(403, "API key management requires a service key")
    return auth


def _key_to_dict(row: ApiKey) -> dict:
    return {
        "id": row.id,
        "kind": row.kind,
        "user_id": row.user_id,
        "name": row.name,
        "key_prefix": row.key_prefix,
        "active": row.active,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
    }


@bp.route("/whoami", methods=["GET"])
def whoami():
    auth = _require_auth()
    user_dict = None
    if auth.user_id is not None:
        user = get_scoped_session().get(User, auth.user_id)
        if user is not None:
            user_dict = {"id": user.id, "username": user.username, "display_name": user.display_name}
    return jsonify({
        "status": "success",
        "kind": auth.kind,
        "key_name": auth.key_name,
        "is_legacy": auth.is_legacy,
        "user": user_dict,
    })


@bp.route("/api_keys", methods=["GET"])
def list_api_keys():
    _require_service()
    session = get_scoped_session()
    rows = session.execute(select(ApiKey).order_by(ApiKey.id)).scalars().all()
    return jsonify({"status": "success", "api_keys": [_key_to_dict(r) for r in rows]})


@bp.route("/api_keys", methods=["POST"])
def create_api_key_endpoint():
    _require_service()
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id")
    if user_id is not None and not isinstance(user_id, int):
        return jsonify({"status": "error", "message": "user_id must be an integer"}), 400
    try:
        row, plaintext = create_api_key(
            get_scoped_session(),
            kind=data.get("kind") or "",
            name=data.get("name") or "",
            user_id=user_id,
        )
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    return jsonify({
        "status": "success",
        "api_key": _key_to_dict(row),
        # the only moment the plaintext leaves the server — it is not stored
        "plaintext": plaintext,
    }), 201


@bp.route("/api_keys/<int:key_id>", methods=["DELETE"])
def deactivate_api_key_endpoint(key_id: int):
    _require_service()
    try:
        row = deactivate_api_key(get_scoped_session(), key_id)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 404
    return jsonify({"status": "success", "api_key": _key_to_dict(row)})
