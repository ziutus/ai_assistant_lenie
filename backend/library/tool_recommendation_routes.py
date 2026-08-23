"""API for the lightweight, provenance-preserving tool recommendation radar."""

import datetime

from flask import Blueprint, abort, g, jsonify, request
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from library.db.engine import get_scoped_session
from library.db.models import Document, ToolRecommendation
from library.tool_recommendation_importer import fetch_markdown, parse_markdown_recommendations

bp = Blueprint("tool_recommendations", __name__)

STATUSES = {"watchlist", "compare", "testing", "adopted", "rejected", "archived"}


def _reader():
    if getattr(g, "auth", None) is None or g.auth.kind not in {"user", "service"}:
        abort(403, "user or service API key required")


def _user():
    if getattr(g, "auth", None) is None or g.auth.kind != "user":
        abort(403, "user API key required")


def _dict(item: ToolRecommendation) -> dict:
    document = item.source_document
    return {
        "id": item.id,
        "name": item.name,
        "homepage_url": item.homepage_url,
        "description": item.description,
        "category": item.category,
        "status": item.status,
        "personal_note": item.personal_note,
        "source_url": item.source_url,
        "source_context": item.source_context,
        "source_document_id": item.source_document_id,
        "source_candidate_id": item.source_candidate_id,
        "source_document": None if document is None else {
            "id": document.id,
            "title": document.title,
            "url": document.url,
            "discovery_source": document.discovery_source.name if document.discovery_source else None,
        },
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


@bp.get("/tool_recommendations")
def get_tool_recommendations():
    _reader()
    status = request.args.get("status", "watchlist")
    if status not in STATUSES and status != "all":
        abort(400, "unsupported status")
    category = request.args.get("category")
    session = get_scoped_session()
    query = select(ToolRecommendation).options(
        joinedload(ToolRecommendation.source_document).joinedload(Document.discovery_source)
    ).order_by(ToolRecommendation.created_at.desc())
    if status != "all":
        query = query.where(ToolRecommendation.status == status)
    if category:
        query = query.where(ToolRecommendation.category == category)
    items = session.execute(query).scalars().all()
    return jsonify({"tool_recommendations": [_dict(item) for item in items], "filters": {"status": status, "category": category}})


@bp.post("/tool_recommendations")
def create_tool_recommendation():
    _user()
    body = request.get_json(silent=True) or {}
    name = str(body.get("name") or "").strip()
    if not name:
        abort(400, "name is required")
    status = body.get("status") or "watchlist"
    if status not in STATUSES:
        abort(400, "unsupported status")
    session = get_scoped_session()
    item = ToolRecommendation(
        name=name[:255], homepage_url=body.get("homepage_url"), description=body.get("description"),
        category=body.get("category"), status=status, personal_note=body.get("personal_note"),
        source_url=body.get("source_url"), source_context=body.get("source_context"),
        source_document_id=body.get("source_document_id"), source_candidate_id=body.get("source_candidate_id"),
    )
    session.add(item)
    session.commit()
    return jsonify({"tool_recommendation": _dict(item)}), 201


@bp.post("/tool_recommendations/import_markdown")
def import_markdown_recommendations():
    """Import a curated GitHub Markdown list into the watchlist, preserving its categories."""
    _user()
    body = request.get_json(silent=True) or {}
    source_url = str(body.get("source_url") or "").strip()
    if not source_url:
        abort(400, "source_url is required")
    try:
        markdown = fetch_markdown(source_url)
    except ValueError as exc:
        abort(400, str(exc))
    except Exception:
        abort(502, "could not fetch GitHub Markdown")
    parsed = parse_markdown_recommendations(markdown)
    session = get_scoped_session()
    created = skipped = 0
    for entry in parsed:
        existing = session.execute(
            select(ToolRecommendation.id).where(
                ToolRecommendation.source_url == source_url,
                func.lower(ToolRecommendation.name) == entry["name"].lower(),
            ).limit(1)
        ).scalar_one_or_none()
        if existing is not None:
            skipped += 1
            continue
        session.add(ToolRecommendation(
            name=entry["name"], homepage_url=entry["homepage_url"], description=entry["description"],
            category=entry["category"], source_url=source_url, source_context="import Markdown", status="watchlist",
        ))
        created += 1
    session.commit()
    return jsonify({"created": created, "skipped": skipped, "parsed": len(parsed)}), 201


@bp.post("/tool_recommendations/<int:recommendation_id>/status")
def update_status(recommendation_id):
    _user()
    body = request.get_json(silent=True) or {}
    status = body.get("status")
    if status not in STATUSES:
        abort(400, "unsupported status")
    session = get_scoped_session()
    item = session.get(ToolRecommendation, recommendation_id)
    if item is None:
        abort(404, "tool recommendation not found")
    item.status = status
    item.personal_note = body.get("personal_note", item.personal_note)
    item.updated_at = datetime.datetime.now(datetime.timezone.utc)
    session.commit()
    return jsonify({"tool_recommendation": _dict(item)})
