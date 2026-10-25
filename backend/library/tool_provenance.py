"""Why a catalog tool was on the radar: the radar entries linked to it through ``tool_recommendations.tool_id``.

The provenance (context text, source link, the document that mentioned it, the catalog lists that
included it) stays on the radar tables - the single source of truth; the catalog reads it through
the link instead of copying it. Read-only, no commits.
"""

from sqlalchemy import select
from sqlalchemy.orm import joinedload, selectinload

from library.db.models import Document, ToolRecommendation, ToolRecommendationEvidence

MAX_EVIDENCES = 10


def _document(document: Document | None) -> dict | None:
    if document is None:
        return None
    return {
        "id": document.id,
        "title": document.title,
        "url": document.url,
        "discovery_source": document.discovery_source.name if document.discovery_source else None,
    }


def radar_for_tools(session, tool_ids: list[int]) -> dict[int, list[dict]]:
    """``{tool_id: [radar origin...]}`` for the catalog cards (two queries for all tools)."""
    if not tool_ids:
        return {}
    entries = session.execute(
        select(ToolRecommendation)
        .where(ToolRecommendation.tool_id.in_(tool_ids))
        .options(
            joinedload(ToolRecommendation.source_document).joinedload(Document.discovery_source),
            selectinload(ToolRecommendation.evidences)
            .joinedload(ToolRecommendationEvidence.recommender_document)
            .joinedload(Document.discovery_source),
        )
        .order_by(ToolRecommendation.created_at)
    ).scalars().all()
    result: dict[int, list[dict]] = {}
    for entry in entries:
        evidences = list(entry.evidences)
        result.setdefault(entry.tool_id, []).append({
            "id": entry.id,
            "status": entry.status,
            "source_context": entry.source_context,
            "source_url": entry.source_url,
            "created_at": entry.created_at.isoformat() if entry.created_at else None,
            "source_document": _document(entry.source_document),
            "evidence_count": len(evidences),
            "evidences": [{
                "relation_type": evidence.relation_type,
                "catalog_label": evidence.catalog_label,
                "catalog_url": evidence.catalog_url,
                "context": evidence.context,
                "recommender_document": _document(evidence.recommender_document),
            } for evidence in evidences[:MAX_EVIDENCES]],
        })
    return result
