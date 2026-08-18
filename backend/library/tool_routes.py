"""REST API for the dynamic "Spis narzedzi" tool catalog view (Epic 46)."""

from flask import Blueprint, abort, g, jsonify, request
from sqlalchemy import select

from library.db.engine import get_scoped_session
from library.db.models import Tool

bp = Blueprint("tools", __name__)


def _reader():
    if getattr(g, "auth", None) is None or g.auth.kind not in {"user", "service"}:
        abort(403, "user or service API key required")


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
