"""Audit trail for refreshes which replace derived document relationships."""

from library.db.models import DocumentRelationshipRemoval


def audit_removals(session, document_id: int, relation_type: str, reason: str, rows, snapshot) -> None:
    for row in rows:
        session.add(DocumentRelationshipRemoval(
            document_id=document_id, relation_type=relation_type,
            original_row_id=getattr(row, "id", None), snapshot=snapshot(row),
            removal_reason=reason,
        ))
