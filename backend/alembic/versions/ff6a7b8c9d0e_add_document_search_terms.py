"""Add generated, user-editable search phrases to documents.

Revision ID: ff6a7b8c9d0e
Revises: fe5f6a7b8c9d
Create Date: 2026-08-11 00:00:00.000000
"""

from alembic import op


revision = "ff6a7b8c9d0e"
down_revision = "fe5f6a7b8c9d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS search_terms TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS search_terms")
