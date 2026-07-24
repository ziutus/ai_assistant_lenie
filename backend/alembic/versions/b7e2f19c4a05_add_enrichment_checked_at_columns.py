"""add enrichment_run_at and entities_checked_at to documents

Revision ID: b7e2f19c4a05
Revises: 5edee6f44633
Create Date: 2026-07-24 16:30:00.000000

Lets the reader UI tell "analysis never ran" apart from "analysis ran and
found nothing" for the Oś czasu/Ton/Okres treści panels (enrichment_run_at,
bumped by refresh_document_events/refresh_document_periods/refresh_document_tones)
and the entities sidebar (entities_checked_at, bumped by
refresh_document_entities) — mirrors the existing ner_unavailable_at pattern,
which only covers the service-down failure case, not "never attempted".
"""
from typing import Sequence, Union

from alembic import op

revision: str = "b7e2f19c4a05"
down_revision: Union[str, None] = "5edee6f44633"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS enrichment_run_at TIMESTAMP")
    op.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS entities_checked_at TIMESTAMP")


def downgrade() -> None:
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS enrichment_run_at")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS entities_checked_at")
