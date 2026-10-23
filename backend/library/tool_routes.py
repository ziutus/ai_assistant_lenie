"""REST API for the dynamic "Spis narzedzi" tool catalog view (Epic 46) and
the human-gated dual write (Epic 47)."""

import datetime

from flask import Blueprint, abort, g, jsonify, request
from sqlalchemy import func, select, update

from library import github_repo_stats, tool_relations_service
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


def _github_url(tool: Tool) -> str | None:
    """The repository the GitHub numbers are looked up for: the explicit link, else a GitHub homepage."""
    if tool.github_url:
        return tool.github_url
    return tool.homepage_url if github_repo_stats.parse_repo_url(tool.homepage_url) else None


def _target_name(session, tool: Tool) -> str | None:
    if not tool.migration_target_tool_id:
        return None
    return session.execute(select(Tool.name).where(Tool.id == tool.migration_target_tool_id)).scalar_one_or_none()


def _tool_dict(
    tool: Tool, relations: list | None = None, github: dict | None = None, target_name: str | None = None,
) -> dict:
    return {
        "relations": relations or [],
        "github": github,
        "id": tool.id,
        "uuid": tool.uuid,
        "name": tool.name,
        "category_tags": tool.category_tags,
        "homepage_url": tool.homepage_url,
        "license": tool.license,
        "pricing": tool.pricing,
        "github_url": tool.github_url,
        "wikipedia_url": tool.wikipedia_url,
        "pricing_url": tool.pricing_url,
        "pricing_type": tool.pricing_type,
        "app_type": tool.app_type,
        "key_points": tool.key_points or [],
        "important_commands": tool.important_commands,
        "migrating_away": bool(tool.migrating_away),
        "migration_note": tool.migration_note,
        "migration_target": {"id": tool.migration_target_tool_id, "name": target_name} if tool.migration_target_tool_id else None,
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
    names = dict(session.execute(select(Tool.id, Tool.name)).all())  # migration targets may fall outside the tag filter
    tools = session.execute(query).scalars().all()
    relations = tool_relations_service.relations_for_tools(session, tools)
    github = github_repo_stats.stats_for_urls(session, [url for url in map(_github_url, tools) if url])
    return jsonify({
        "tools": [
            _tool_dict(tool, relations.get(tool.id), github.get(_github_url(tool)), names.get(tool.migration_target_tool_id))
            for tool in tools
        ],
        "filters": {"tag": tag},
    })


@bp.post("/tools/github_stats/refresh")
def refresh_github_stats():
    """Pull fresh GitHub numbers for the catalog's repositories, a bounded batch per call (shared table with the radar)."""
    _user()
    body = request.get_json(silent=True) or {}
    try:
        limit = int(body.get("limit", github_repo_stats.DEFAULT_REFRESH_LIMIT))
    except (TypeError, ValueError):
        abort(400, "limit must be an integer")
    if not 1 <= limit <= github_repo_stats.MAX_REFRESH_LIMIT:
        abort(400, f"limit must be between 1 and {github_repo_stats.MAX_REFRESH_LIMIT}")
    session = get_scoped_session()
    tools = session.execute(select(Tool)).scalars().all()
    summary = github_repo_stats.refresh_stale(session, [url for url in map(_github_url, tools) if url], limit=limit)
    session.commit()
    return jsonify(summary)


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
        category_tags=[],
        key_points=[],
        migrating_away=False,
        source_document_id=body.get("source_document_id"),
        source_candidate_id=body.get("source_candidate_id"),
        status="accepted",
    )
    _apply_fields(tool, body)
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
MAX_KEY_POINTS = 50
MAX_KEY_POINT_LENGTH = 500
PRICING_TYPES = {"free", "freemium", "paid", "subscription", "usage_based", "open_core"}
# Fields kept verbatim (markdown / commands); the other text fields are trimmed. An empty value clears.
MULTILINE_FIELDS = ("personal_notes", "important_commands", "migration_note")
SHORT_TEXT_FIELDS = ("license", "pricing", "app_type")
URL_FIELDS = ("homepage_url", "github_url", "wikipedia_url", "pricing_url")


def _text_field(body: dict, field: str) -> tuple[bool, str | None]:
    if field not in body:
        return False, None
    value = body[field]
    if value is not None and not isinstance(value, str):
        abort(400, f"{field} must be a string or null")
    text = value if field in MULTILINE_FIELDS else (value or "").strip()
    return True, text if text and text.strip() else None


def _apply_fields(tool: Tool, body: dict) -> None:
    """Copy the editable catalog fields present in ``body`` onto ``tool``; aborts 400 on a bad value."""
    for field in (*MULTILINE_FIELDS, *SHORT_TEXT_FIELDS):
        present, text = _text_field(body, field)
        if present:
            setattr(tool, field, text)
    for field in URL_FIELDS:
        present, text = _text_field(body, field)
        if not present:
            continue
        if text is not None and not text.lower().startswith(("http://", "https://")):
            abort(400, f"{field} must start with http:// or https://")
        if field == "github_url" and text is not None and github_repo_stats.parse_repo_url(text) is None:
            abort(400, "github_url must point at a github.com/owner/repo repository")
        setattr(tool, field, text)
    present, pricing_type = _text_field(body, "pricing_type")
    if present:
        if pricing_type is not None and pricing_type not in PRICING_TYPES:
            abort(400, f"pricing_type must be one of: {', '.join(sorted(PRICING_TYPES))}")
        tool.pricing_type = pricing_type
    if "category_tags" in body:
        tags = body["category_tags"]
        if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags) or len(tags) > MAX_TAGS:
            abort(400, "category_tags must be a list of strings")
        tool.category_tags = list(dict.fromkeys(tag.strip()[:MAX_TAG_LENGTH] for tag in tags if tag.strip()))
    if "key_points" in body:
        points = body["key_points"]
        if not isinstance(points, list) or not all(isinstance(point, str) for point in points) or len(points) > MAX_KEY_POINTS:
            abort(400, "key_points must be a list of strings")
        tool.key_points = [point.strip()[:MAX_KEY_POINT_LENGTH] for point in points if point.strip()]
    if "migrating_away" in body:
        if not isinstance(body["migrating_away"], bool):
            abort(400, "migrating_away must be a boolean")
        tool.migrating_away = body["migrating_away"]
        if not tool.migrating_away:
            tool.migration_target_tool_id = None
    if "migration_target_tool_id" in body:
        target_id = body["migration_target_tool_id"]
        if target_id is not None:
            if not isinstance(target_id, int) or isinstance(target_id, bool):
                abort(400, "migration_target_tool_id must be a tool id or null")
            if tool.id is not None and target_id == tool.id:
                abort(400, "a tool cannot be migrated to itself")
            if get_scoped_session().get(Tool, target_id) is None:
                abort(400, "migration_target_tool_id does not exist")
        # A target only makes sense while the tool is being phased out.
        tool.migration_target_tool_id = target_id if tool.migrating_away else None


@bp.patch("/tools/<int:tool_id>")
def update_tool(tool_id):
    """Edit the catalog entry in Lenie itself: note, tags, links, licence, pricing, key points, migrating away."""
    _user()
    body = request.get_json(silent=True) or {}
    session = get_scoped_session()
    tool = session.get(Tool, tool_id)
    if tool is None:
        abort(404, "tool not found")
    _apply_fields(tool, body)
    tool.updated_at = datetime.datetime.now(datetime.timezone.utc)
    session.commit()
    return jsonify({"tool": _tool_dict(tool, target_name=_target_name(session, tool))})


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
