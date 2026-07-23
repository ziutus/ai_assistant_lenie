"""Durable audit records for manual entity-review decisions."""

from __future__ import annotations

from library.db.models import EntityReviewDecision


def record_entity_decision(
    session,
    *,
    document_id: int | None,
    entity_type: str,
    entity_text: str,
    decision: str,
    reason_code: str | None = None,
    comment: str | None = None,
    document_entity_id: int | None = None,
    document_person_id: int | None = None,
    person_id: int | None = None,
    original_confidence: str | None = None,
    replacement_person_id: int | None = None,
    source_excerpt: str | None = None,
    details: dict | None = None,
) -> EntityReviewDecision:
    """Append an audit row in the caller's transaction."""
    row = EntityReviewDecision(
        document_id=document_id,
        document_entity_id=document_entity_id,
        document_person_id=document_person_id,
        person_id=person_id,
        entity_type=entity_type,
        entity_text=entity_text,
        decision=decision,
        reason_code=reason_code,
        comment=comment,
        original_confidence=original_confidence,
        replacement_person_id=replacement_person_id,
        source_excerpt=source_excerpt,
        details=details,
    )
    session.add(row)
    return row
