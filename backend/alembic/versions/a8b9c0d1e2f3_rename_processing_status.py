"""rename document_state to processing_status (columns + lookup tables)

Stage 11g part 2a of docs/search-rebuild-implementation-plan.md:
- documents.document_state       -> documents.processing_status
- documents.document_state_error -> documents.processing_error_code
- lookup document_status_types        -> processing_status_types
- lookup document_status_error_types  -> processing_error_types
Values (the 15 pipeline states / 14 error codes) stay identical.

Revision ID: a8b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-07-19 07:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "a8b9c0d1e2f3"
down_revision: Union[str, None] = "f7a8b9c0d1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE document_status_types RENAME TO processing_status_types")
    op.execute("ALTER TABLE document_status_error_types RENAME TO processing_error_types")
    op.execute("ALTER TABLE documents RENAME COLUMN document_state TO processing_status")
    op.execute("ALTER TABLE documents RENAME COLUMN document_state_error TO processing_error_code")
    op.execute("ALTER TABLE documents RENAME CONSTRAINT fk_document_state TO fk_processing_status")
    op.execute("ALTER TABLE documents RENAME CONSTRAINT fk_document_state_error TO fk_processing_error_code")
    op.execute("ALTER INDEX idx_documents_document_state RENAME TO idx_documents_processing_status")


def downgrade() -> None:
    op.execute("ALTER INDEX idx_documents_processing_status RENAME TO idx_documents_document_state")
    op.execute("ALTER TABLE documents RENAME CONSTRAINT fk_processing_error_code TO fk_document_state_error")
    op.execute("ALTER TABLE documents RENAME CONSTRAINT fk_processing_status TO fk_document_state")
    op.execute("ALTER TABLE documents RENAME COLUMN processing_error_code TO document_state_error")
    op.execute("ALTER TABLE documents RENAME COLUMN processing_status TO document_state")
    op.execute("ALTER TABLE processing_error_types RENAME TO document_status_error_types")
    op.execute("ALTER TABLE processing_status_types RENAME TO document_status_types")
