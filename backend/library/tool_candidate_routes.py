"""REST API for reviewing Bielik-detected tool candidates (Epic 44)."""

import datetime

from flask import Blueprint, abort, g, jsonify, request
from sqlalchemy import select, func
from sqlalchemy.orm import joinedload

from library.db.engine import get_scoped_session
from library.db.models import Document, DiscoverySource, Tool, ToolCandidate

bp = Blueprint("tool_candidates", __name__)

DUPLICATE_SIMILARITY_THRESHOLD = 0.5  # matches library.person_registry.FUZZY_SIMILARITY_THRESHOLD


def _reader():
    if getattr(g, "auth", None) is None or g.auth.kind not in {"user", "service"}:
        abort(403, "user or service API key required")


def _user():
    if getattr(g, "auth", None) is None or g.auth.kind != "user":
        abort(403, "user API key required")


def _get_candidate_with_document(session, candidate_id: int):
    row = (
        session.execute(
            select(ToolCandidate, Document)
            .join(Document, Document.id == ToolCandidate.source_document_id)
            .options(joinedload(Document.discovery_source))
            .where(ToolCandidate.id == candidate_id)
        )
        .first()
    )
    if row is None:
        abort(404, "tool candidate not found")
    return row


def _find_similar_tool_name(session, name: str) -> str | None:
    tool = session.execute(
        select(Tool)
        .where(func.similarity(Tool.name, name) > DUPLICATE_SIMILARITY_THRESHOLD)
        .order_by(func.similarity(Tool.name, name).desc())
        .limit(1)
    ).scalars().first()
    return tool.name if tool is not None else None


def _candidate_dict(candidate: ToolCandidate, document: Document) -> dict:
    return {
        "id": candidate.id,
        "name": candidate.name,
        "status": candidate.status,
        "context_snippet": candidate.context_snippet,
        "detected_by": candidate.detected_by,
        "created_at": candidate.created_at.isoformat() if candidate.created_at else None,
        "reviewed_at": candidate.reviewed_at.isoformat() if candidate.reviewed_at else None,
        "source_document_id": candidate.source_document_id,
        "source_document": {
            "id": document.id,
            "title": document.title,
            "url": document.url,
            "byline": document.byline,
            "discovery_source": document.discovery_source.name if document.discovery_source else None,
            "published_on": document.published_on.isoformat() if document.published_on else None,
            "ingested_at": document.ingested_at.isoformat() if document.ingested_at else None,
        },
    }


@bp.get("/tool_candidates")
def get_tool_candidates():
    _reader()
    session = get_scoped_session()
    status = request.args.get("status", "pending")
    allowed_statuses = {"pending", "accepted", "rejected", "deferred"}
    if status not in allowed_statuses:
        abort(400, "unsupported status")
    source = request.args.get("source")
    query = (
        select(ToolCandidate, Document)
        .join(Document, Document.id == ToolCandidate.source_document_id)
        .options(joinedload(Document.discovery_source))
        .where(ToolCandidate.status == status)
        .order_by(ToolCandidate.created_at.desc())
    )
    if source:
        source_ids = select(DiscoverySource.id).where(
            func.unaccent(func.lower(DiscoverySource.name)) == func.unaccent(source.strip().lower())
        )
        query = query.where(Document.discovery_source_id.in_(source_ids))
    rows = session.execute(query).all()
    return jsonify({
        "tool_candidates": [_candidate_dict(candidate, document) for candidate, document in rows],
        "filters": {"status": status, "source": source},
    })


@bp.get("/tool_candidates/<int:candidate_id>")
def get_tool_candidate(candidate_id):
    _reader()
    session = get_scoped_session()
    candidate, document = _get_candidate_with_document(session, candidate_id)
    return jsonify({"tool_candidate": _candidate_dict(candidate, document)})


@bp.post("/tool_candidates/<int:candidate_id>/accept")
def accept_candidate(candidate_id):
    _user()
    session = get_scoped_session()
    candidate, document = _get_candidate_with_document(session, candidate_id)
    candidate.status = "accepted"
    candidate.reviewed_at = datetime.datetime.now(datetime.timezone.utc)
    warning = None
    similar_name = _find_similar_tool_name(session, candidate.name)
    if similar_name is not None:
        warning = f"Możliwy duplikat: w bazie istnieje już podobne narzędzie „{similar_name}”."
    session.commit()
    return jsonify({"tool_candidate": _candidate_dict(candidate, document), "warning": warning})


@bp.post("/tool_candidates/<int:candidate_id>/reject")
def reject_candidate(candidate_id):
    _user()
    session = get_scoped_session()
    candidate, document = _get_candidate_with_document(session, candidate_id)
    candidate.status = "rejected"
    candidate.reviewed_at = datetime.datetime.now(datetime.timezone.utc)
    session.commit()
    return jsonify({"tool_candidate": _candidate_dict(candidate, document)})


@bp.post("/tool_candidates/<int:candidate_id>/defer")
def defer_candidate(candidate_id):
    _user()
    session = get_scoped_session()
    candidate, document = _get_candidate_with_document(session, candidate_id)
    candidate.status = "deferred"
    candidate.reviewed_at = datetime.datetime.now(datetime.timezone.utc)
    session.commit()
    return jsonify({"tool_candidate": _candidate_dict(candidate, document)})
