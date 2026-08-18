"""REST API for reviewing Bielik-detected tool candidates (Epic 44)."""

from flask import Blueprint, abort, g, jsonify, request
from sqlalchemy import select, func
from sqlalchemy.orm import joinedload

from library.db.engine import get_scoped_session
from library.db.models import Document, DiscoverySource, ToolCandidate

bp = Blueprint("tool_candidates", __name__)


def _reader():
    if getattr(g, "auth", None) is None or g.auth.kind not in {"user", "service"}:
        abort(403, "user or service API key required")


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
