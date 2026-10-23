"""REST API for the dynamic "Spis narzedzi" tool catalog view (Epic 46) and
the human-gated dual write (Epic 47)."""

import datetime

from flask import Blueprint, abort, g, jsonify, request
from sqlalchemy import func, select, update

from library import tool_relations_service
from library.db.engine import get_scoped_session
from library.db.models import ObsidianNoteVersion, Tool, ToolRecommendation
from library.obsidian_vault import (
    VaultPathInvalidError,
    ensure_within_vault,
    is_vault_mount_available,
    retry_write_note,
    write_note_with_version,
)

bp = Blueprint("tools", __name__)


def _reader():
    if getattr(g, "auth", None) is None or g.auth.kind not in {"user", "service"}:
        abort(403, "user or service API key required")


def _user():
    if getattr(g, "auth", None) is None or g.auth.kind != "user":
        abort(403, "user API key required")


def _tool_dict(tool: Tool, relations: list | None = None) -> dict:
    return {
        "relations": relations or [],
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
    relations = tool_relations_service.relations_for_tools(session, tools)
    return jsonify({
        "tools": [_tool_dict(tool, relations.get(tool.id)) for tool in tools],
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
    if not name:
        abort(400, "name is required")
    # The Obsidian note is optional: Lenie keeps the tool's own note in personal_notes. The vault
    # write (Epic 47) still happens when a note is supplied, and then needs both fields.
    with_obsidian = bool(note_path or content)
    if with_obsidian:
        if not note_path or not content:
            abort(400, "note_path and content must be sent together")
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
    # A radar entry of the same name that is not linked yet now points at the new catalog tool.
    session.execute(
        update(ToolRecommendation)
        .where(func.lower(ToolRecommendation.name) == tool.name.strip().lower(), ToolRecommendation.tool_id.is_(None))
        .values(tool_id=tool.id)
    )

    if not with_obsidian:
        session.commit()
        return jsonify({"written": False, "obsidian": False, "tool_id": tool.id, "path": None}), 201

    try:
        write_note_with_version(session, note_path, content, tool_id=tool.id, user_prompt=body.get("user_prompt"))
    except Exception:
        # DB commit already happened inside write_note_with_version() before the
        # file write was attempted -- do NOT roll back (FR20). The mount check
        # runs only here, after a write has already failed, to distinguish a
        # disconnected/unreachable volume (sync_container_unavailable) from a
        # reachable volume that failed to write for another reason (disk full,
        # permissions -- obsidian_write_failed). It never polls
        # obsidian-headless-sync's own health.
        if not is_vault_mount_available():
            error = "sync_container_unavailable"
            hint = (
                "Sprawdź, czy kontener obsidian-headless-sync działa i synchronizacja "
                "wolumenu jest aktywna, następnie ponów zapis."
            )
        else:
            error = "obsidian_write_failed"
            hint = "Sprawdź zasoby na wolumenie NAS (miejsce na dysku, uprawnienia do zapisu) i ponów zapis."
        response = jsonify({"written": False, "error": error, "tool_id": tool.id, "hint": hint})
        response.status_code = 502
        return response

    tool.obsidian_note_path = note_path
    session.commit()
    return jsonify({"written": True, "tool_id": tool.id, "path": note_path})


MAX_TAGS = 30
MAX_TAG_LENGTH = 60
EDITABLE_TEXT_FIELDS = ("homepage_url", "license", "pricing", "personal_notes")


@bp.patch("/tools/<int:tool_id>")
def update_tool(tool_id):
    """Edit the catalog entry in Lenie itself: note (``personal_notes``), tags, homepage, licence, pricing."""
    _user()
    body = request.get_json(silent=True) or {}
    session = get_scoped_session()
    tool = session.get(Tool, tool_id)
    if tool is None:
        abort(404, "tool not found")
    for field in EDITABLE_TEXT_FIELDS:
        if field in body:
            value = body[field]
            if value is not None and not isinstance(value, str):
                abort(400, f"{field} must be a string or null")
            # The note keeps its own whitespace (markdown); the short fields are trimmed. Empty clears.
            text = value if field == "personal_notes" else (value or "").strip()
            setattr(tool, field, text if text and text.strip() else None)
    if "category_tags" in body:
        tags = body["category_tags"]
        if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags) or len(tags) > MAX_TAGS:
            abort(400, "category_tags must be a list of strings")
        tool.category_tags = list(dict.fromkeys(tag.strip()[:MAX_TAG_LENGTH] for tag in tags if tag.strip()))
    tool.updated_at = datetime.datetime.now(datetime.timezone.utc)
    session.commit()
    return jsonify({"tool": _tool_dict(tool)})


@bp.post("/tools/<int:tool_id>/retry_obsidian_write")
def retry_obsidian_write(tool_id):
    _user()
    session = get_scoped_session()

    # SELECT ... FOR UPDATE: holds a row lock on this Tool for the rest of the
    # transaction so two concurrent retries can't both observe
    # obsidian_note_path IS NULL and both write -- the second blocks here
    # until the first commits (or rolls back on abort/error), then re-reads
    # the now-updated row and correctly hits the already_written branch.
    tool = session.execute(select(Tool).where(Tool.id == tool_id).with_for_update()).scalar_one_or_none()
    if tool is None:
        abort(404, "tool not found")

    if tool.obsidian_note_path is not None:
        response = jsonify({
            "written": False,
            "error": "already_written",
            "tool_id": tool.id,
            "path": tool.obsidian_note_path,
            "hint": "To narzędzie ma już zapisaną notatkę w Obsidian — retry nie jest potrzebny.",
        })
        response.status_code = 409
        return response

    version = session.execute(
        select(ObsidianNoteVersion)
        .where(ObsidianNoteVersion.tool_id == tool_id)
        .order_by(ObsidianNoteVersion.created_at.desc())
        .limit(1)
    ).scalars().first()
    if version is None:
        abort(404, "no obsidian_note_versions row found for this tool")

    try:
        retry_write_note(session, version.note_path, version.content_after)
    except Exception:
        # Same mount-reachability check as create_tool()'s error branch (Story
        # 47.3) -- distinguishes a disconnected/unreachable volume from a
        # reachable volume that failed to write for another reason.
        if not is_vault_mount_available():
            error = "sync_container_unavailable"
            hint = (
                "Sprawdź, czy kontener obsidian-headless-sync działa i synchronizacja "
                "wolumenu jest aktywna, następnie ponów zapis."
            )
        else:
            error = "obsidian_write_failed"
            hint = "Sprawdź zasoby na wolumenie NAS (miejsce na dysku, uprawnienia do zapisu) i ponów zapis."
        response = jsonify({"written": False, "error": error, "tool_id": tool.id, "hint": hint})
        response.status_code = 502
        return response

    tool.obsidian_note_path = version.note_path
    session.commit()
    return jsonify({"written": True, "tool_id": tool.id, "path": version.note_path})
