"""rename documents.created_at to ingested_at; document_time_periods.period_* to subject_period_*

Stage 11g part 2b of docs/search-rebuild-implementation-plan.md. Only the
documents table's created_at is renamed — every other table keeps its own
created_at (row creation time); ingested_at specifically means "when the
document entered Lenie", distinct from published_on.

Revision ID: b9c0d1e2f3a4
Revises: a8b9c0d1e2f3
Create Date: 2026-07-19 08:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "b9c0d1e2f3a4"
down_revision: Union[str, None] = "a8b9c0d1e2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE documents RENAME COLUMN created_at TO ingested_at")
    op.execute("ALTER INDEX idx_documents_created_at RENAME TO idx_documents_ingested_at")
    op.execute("ALTER TABLE document_time_periods RENAME COLUMN period_label TO subject_period_label")
    op.execute("ALTER TABLE document_time_periods RENAME COLUMN period_start_year TO subject_period_start_year")
    op.execute("ALTER TABLE document_time_periods RENAME COLUMN period_end_year TO subject_period_end_year")


def downgrade() -> None:
    op.execute("ALTER TABLE document_time_periods RENAME COLUMN subject_period_end_year TO period_end_year")
    op.execute("ALTER TABLE document_time_periods RENAME COLUMN subject_period_start_year TO period_start_year")
    op.execute("ALTER TABLE document_time_periods RENAME COLUMN subject_period_label TO period_label")
    op.execute("ALTER INDEX idx_documents_ingested_at RENAME TO idx_documents_created_at")
    op.execute("ALTER TABLE documents RENAME COLUMN ingested_at TO created_at")
