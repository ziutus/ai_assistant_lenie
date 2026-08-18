"""REST API for the dynamic "Spis narzedzi" tool catalog view (Epic 46) and
the human-gated dual write (Epic 47)."""

from flask import Blueprint, abort, g, jsonify, request
from sqlalchemy import select

from library.db.engine import get_scoped_session
from library.db.models import Tool
from library.obsidian_vault import VaultPathInvalidError, ensure_within_vault, write_note_with_version

bp = Blueprint("tools", __name__)


def _reader():
    if getattr(g, "auth", None) is None or g.auth.kind not in {"user", "service"}:
        abort(403, "user or service API key required")


def _user():
    if getattr(g, "auth", None) is None or g.auth.kind != "user":
        abort(403, "user API key required")


def _tool_dict(tool: Tool) -> dict:
    return {
        "id": tool.id,
        "uuid": tool.uuid,
        "name": tool.name,
        "category_tags": tool.category_tags,
        "homepage_url": tool.homepage_url,
        "license": tool.license,
        "pricing": tool.pricing,
        "personal_notes": tool.personal_notes,
        "source_document_id": tool.source_document_id,
        "source_candidate_id": tool.source_candidate_id,
        "status": tool.status,
        "obsidian_note_path": tool.obsidian_note_path,
        "created_at": tool.created_at.isoformat() if tool.created_at else None,
        "updated_at": tool.updated_at.isoformat() if tool.updated_at else None,
    }


@bp.get("/tools")
def get_tools():
    _reader()
    session = get_scoped_session()
    tag = request.args.get("tag")
    query = select(Tool).order_by(Tool.name)
    if tag:
        query = query.where(Tool.category_tags.contains([tag]))
    tools = session.execute(query).scalars().all()
    return jsonify({
        "tools": [_tool_dict(tool) for tool in tools],
        "filters": {"tag": tag},
    })


@bp.post("/tools")
def create_tool():
    _user()
    session = get_scoped_session()

    body = request.get_json(silent=True) or {}
    note_path = body.get("note_path")
    content = body.get("content")
    name = body.get("name")
    if not note_path or not content or not name:
        abort(400, "name, note_path and content are required")

    try:
        ensure_within_vault(note_path)
    except VaultPathInvalidError:
        abort(400, "note_path escapes vault root")

    tool = Tool(
        name=name,
        category_tags=body.get("category_tags") or [],
        homepage_url=body.get("homepage_url"),
        license=body.get("license"),
        pricing=body.get("pricing"),
        personal_notes=body.get("personal_notes"),
        source_document_id=body.get("source_document_id"),
        source_candidate_id=body.get("source_candidate_id"),
        status="accepted",
    )
    session.add(tool)
    session.flush()

    try:
        write_note_with_version(session, note_path, content, tool_id=tool.id, user_prompt=body.get("user_prompt"))
    except Exception:
        # DB commit already happened inside write_note_with_version() before the
        # file write was attempted -- do NOT roll back (FR20). Distinguishing
        # sync_container_unavailable from a generic write failure is Story 47.3's
        # job, applied to this same except branch.
        response = jsonify({"written": False, "error": "obsidian_write_failed", "tool_id": tool.id})
        response.status_code = 502
        return response

    tool.obsidian_note_path = note_path
    session.commit()
    return jsonify({"written": True, "tool_id": tool.id, "path": note_path})
