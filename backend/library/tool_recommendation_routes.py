"""API for the lightweight, provenance-preserving tool recommendation radar."""

import datetime
from urllib.parse import urlparse

from flask import Blueprint, abort, g, jsonify, request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import joinedload, selectinload

from library.db.engine import get_scoped_session
from library.db.models import Document, Tool, ToolRecommendation, ToolRecommendationEvidence
from library.tool_recommendation_importer import fetch_markdown, parse_markdown_recommendations

bp = Blueprint("tool_recommendations", __name__)

STATUSES = {"watchlist", "compare", "testing", "adopted", "rejected", "archived"}


def _existing_tool(session, name: str, homepage_url: str | None = None) -> Tool | None:
    clauses = [func.lower(Tool.name) == name.strip().lower()]
    if homepage_url:
        clauses.append(Tool.homepage_url == homepage_url)
    return session.execute(select(Tool).where(or_(*clauses)).limit(1)).scalars().first()


def _ensure_tool(session, item: ToolRecommendation) -> tuple[Tool, bool]:
    existing = _existing_tool(session, item.name, item.homepage_url)
    if existing is not None:
        return existing, False
    tool = Tool(
        name=item.name,
        homepage_url=item.homepage_url,
        category_tags=[item.category] if item.category else [],
        personal_notes=item.personal_note,
        source_document_id=item.source_document_id,
        source_candidate_id=item.source_candidate_id,
        status="accepted",
    )
    session.add(tool)
    session.flush()
    return tool, True


def _catalog_label(url: str) -> str:
    parsed = urlparse(url)
    path = [part for part in parsed.path.split("/") if part]
    if parsed.netloc.lower().endswith("github.com") and len(path) >= 2:
        return f"{path[0]}/{path[1]}"
    return parsed.netloc or url


def _resolve_source_document(session, source_url: str, requested_id: int | None) -> Document | None:
    """Use an explicit document as an override, otherwise resolve the catalog URL.

    A saved LinkDocument often carries its discovery source (for example a
    newsletter), so resolving the URL here preserves the whole recommendation
    path without making a user copy an internal numeric ID.
    """
    if requested_id is not None:
        document = session.get(Document, requested_id)
        if document is None:
            abort(404, "source document not found")
        return document
    return session.execute(
        select(Document)
        .where(or_(Document.url == source_url, Document.canonical_url == source_url))
        .order_by(Document.ingested_at.desc(), Document.id.desc())
        .limit(1)
    ).scalars().first()


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
        "origin": "ai_detected" if item.source_candidate_id is not None else "curated",
        "source_document": None if document is None else {
            "id": document.id,
            "title": document.title,
            "url": document.url,
            "discovery_source": document.discovery_source.name if document.discovery_source else None,
        },
        "evidences": [{
            "id": evidence.id,
            "relation_type": evidence.relation_type,
            "catalog_url": evidence.catalog_url,
            "catalog_label": evidence.catalog_label,
            "context": evidence.context,
            "recommender_document": None if evidence.recommender_document is None else {
                "id": evidence.recommender_document.id,
                "title": evidence.recommender_document.title,
                "url": evidence.recommender_document.url,
                "discovery_source": evidence.recommender_document.discovery_source.name if evidence.recommender_document.discovery_source else None,
            },
        } for evidence in getattr(item, "evidences", [])],
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
    origin = request.args.get("origin", "all")
    if origin not in {"all", "ai_detected", "curated"}:
        abort(400, "unsupported origin")
    session = get_scoped_session()
    query = select(ToolRecommendation).options(
        joinedload(ToolRecommendation.source_document).joinedload(Document.discovery_source),
        selectinload(ToolRecommendation.evidences)
        .joinedload(ToolRecommendationEvidence.recommender_document)
        .joinedload(Document.discovery_source),
    ).order_by(ToolRecommendation.created_at.desc())
    if status != "all":
        query = query.where(ToolRecommendation.status == status)
    if category:
        query = query.where(ToolRecommendation.category == category)
    if origin == "ai_detected":
        query = query.where(ToolRecommendation.source_candidate_id.is_not(None))
    if origin == "curated":
        query = query.where(ToolRecommendation.source_candidate_id.is_(None))
    items = session.execute(query).scalars().all()
    categories = session.execute(
        select(ToolRecommendation.category)
        .where(ToolRecommendation.category.is_not(None))
        .distinct()
        .order_by(ToolRecommendation.category)
    ).scalars().all()
    return jsonify({
        "tool_recommendations": [_dict(item) for item in items],
        "categories": categories,
        "filters": {"status": status, "category": category, "origin": origin},
    })


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
    existing_tool = _existing_tool(session, name, body.get("homepage_url"))
    if existing_tool is not None:
        return jsonify({"existing_tool": {"id": existing_tool.id, "name": existing_tool.name}}), 200
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
    source_document_id = body.get("source_document_id")
    if source_document_id is not None:
        try:
            source_document_id = int(source_document_id)
        except (TypeError, ValueError):
            abort(400, "source_document_id must be an integer")
    try:
        markdown = fetch_markdown(source_url)
    except ValueError as exc:
        abort(400, str(exc))
    except Exception:
        abort(502, "could not fetch GitHub Markdown")
    parsed = parse_markdown_recommendations(markdown)
    session = get_scoped_session()
    source_document = _resolve_source_document(session, source_url, source_document_id)
    created = skipped = evidence_created = evidence_upgraded = tools_skipped = 0
    linked_existing = 0
    skipped_items = []
    for entry in parsed:
        if _existing_tool(session, entry["name"], entry["homepage_url"]) is not None:
            tools_skipped += 1
            skipped_items.append({"name": entry["name"], "reason": "already_in_tools"})
            continue
        item = session.execute(
            select(ToolRecommendation).where(
                or_(
                    ToolRecommendation.homepage_url == entry["homepage_url"],
                    func.lower(ToolRecommendation.name) == entry["name"].lower(),
                ),
            ).limit(1)
        ).scalar_one_or_none()
        if item is not None:
            skipped += 1
            if source_document is not None and item.source_document_id is None:
                item.source_document_id = source_document.id
                linked_existing += 1
            skipped_items.append({"name": entry["name"], "existing_id": item.id, "reason": "already_in_radar"})
        else:
            item = ToolRecommendation(
                name=entry["name"], homepage_url=entry["homepage_url"], description=entry["description"],
                category=entry["category"], source_url=source_url, source_context="Katalog GitHub",
                source_document_id=source_document.id if source_document is not None else None, status="watchlist",
            )
            session.add(item)
            session.flush()
            created += 1

        evidence = session.execute(select(ToolRecommendationEvidence).where(
            ToolRecommendationEvidence.tool_recommendation_id == item.id,
            ToolRecommendationEvidence.catalog_url == source_url,
            ToolRecommendationEvidence.recommender_document_id == (source_document.id if source_document else None),
        ).limit(1)).scalar_one_or_none()
        if evidence is None and source_document is not None:
            # Imports made before graph provenance had a catalog edge without
            # an upstream document. Upgrade that edge in place during a
            # re-import so the UI shows one coherent path, not a duplicate.
            evidence = session.execute(select(ToolRecommendationEvidence).where(
                ToolRecommendationEvidence.tool_recommendation_id == item.id,
                ToolRecommendationEvidence.catalog_url == source_url,
                ToolRecommendationEvidence.recommender_document_id.is_(None),
            ).limit(1)).scalar_one_or_none()
            if evidence is not None:
                evidence.recommender_document_id = source_document.id
                evidence.catalog_label = _catalog_label(source_url)
                evidence.context = entry["category"]
                evidence_upgraded += 1
        if evidence is None:
            session.add(ToolRecommendationEvidence(
                tool_recommendation_id=item.id, relation_type="listed_in", catalog_url=source_url,
                catalog_label=_catalog_label(source_url), context=entry["category"],
                recommender_document_id=source_document.id if source_document else None,
            ))
            evidence_created += 1
    session.commit()
    return jsonify({
        "created": created,
        "skipped": skipped,
        "skipped_items": skipped_items,
        "linked_existing": linked_existing,
        "evidence_created": evidence_created,
        "evidence_upgraded": evidence_upgraded,
        "tools_skipped": tools_skipped,
        "resolved_source_document": None if source_document is None else {
            "id": source_document.id,
            "title": source_document.title,
            "discovery_source": source_document.discovery_source.name if source_document.discovery_source else None,
        },
        "parsed": len(parsed),
    }), 201


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
    tool = created = None
    if status == "adopted":
        tool, created = _ensure_tool(session, item)
    session.commit()
    return jsonify({"tool_recommendation": _dict(item), "tool": None if tool is None else {"id": tool.id, "name": tool.name}, "tool_created": created})


@bp.post("/tool_recommendations/bulk_status")
def bulk_update_status():
    """Move a deliberate selection of radar entries to one lifecycle stage."""
    _user()
    body = request.get_json(silent=True) or {}
    status = body.get("status")
    raw_ids = body.get("ids")
    if status not in STATUSES:
        abort(400, "unsupported status")
    if not isinstance(raw_ids, list) or not raw_ids or len(raw_ids) > 1000:
        abort(400, "ids must contain between 1 and 1000 recommendation IDs")
    try:
        ids = sorted({int(item) for item in raw_ids})
    except (TypeError, ValueError):
        abort(400, "ids must be integers")
    session = get_scoped_session()
    items = session.execute(select(ToolRecommendation).where(ToolRecommendation.id.in_(ids))).scalars().all()
    now = datetime.datetime.now(datetime.timezone.utc)
    tools_created = []
    for item in items:
        item.status = status
        item.updated_at = now
        if status == "adopted":
            tool, created = _ensure_tool(session, item)
            if created:
                tools_created.append(tool.id)
    session.commit()
    return jsonify({"updated": len(items), "status": status, "tools_created": tools_created})
