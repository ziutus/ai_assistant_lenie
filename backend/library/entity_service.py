"""Persist NER entities (persons/places) per document — MVP of docs/ner-integration-plan.md.

Sits between the NER client (library/ner_client.py) and the document_entities
table: extract → aggregate by (type, base form) → replace the document's rows.
Entities are derived data, so a refresh replaces previous rows instead of
merging (unlike doc.tags, which accumulates across runs).
"""

import logging

from sqlalchemy import delete

from library.db.models import DocumentEntity
from library.ner_client import aggregate_entities, extract_entities

logger = logging.getLogger(__name__)


def refresh_document_entities(session, document_id: int, text: str) -> list[DocumentEntity]:
    """Run NER on text and replace the document's rows in document_entities.

    Queues the changes on the session without committing (caller owns the
    transaction). Returns the new DocumentEntity rows. When the NER service is
    unavailable an empty extraction result leaves existing rows untouched —
    "service down" must not erase previously detected entities.
    """
    raw = extract_entities(text)
    if not raw:
        return []

    counts = aggregate_entities(raw)
    session.execute(delete(DocumentEntity).where(DocumentEntity.document_id == document_id))
    rows = [
        DocumentEntity(
            document_id=document_id,
            entity_type=entity_type,
            entity_text=entity_text,
            mention_count=count,
        )
        for (entity_type, entity_text), count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    session.add_all(rows)
    return rows


def get_document_entities(session, document_id: int) -> dict[str, list[dict]]:
    """Return the document's stored entities grouped by type, most-mentioned first.

    Shape: {"persName": [{"text": ..., "count": ...}, ...], "geogName": [...], "placeName": [...]}
    """
    rows = (
        session.query(DocumentEntity)
        .filter(DocumentEntity.document_id == document_id)
        .order_by(DocumentEntity.mention_count.desc(), DocumentEntity.entity_text)
        .all()
    )
    grouped: dict[str, list[dict]] = {"persName": [], "geogName": [], "placeName": []}
    for row in rows:
        grouped.setdefault(row.entity_type, []).append(
            {"text": row.entity_text, "count": row.mention_count}
        )
    return grouped
