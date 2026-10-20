"""Add a long description and external links to persons.

Revision ID: b8d2f4a61c93
Revises: a71c9e2b406d
Create Date: 2026-10-20 00:00:00.000000
"""

from alembic import op


revision = "b8d2f4a61c93"
down_revision = "a71c9e2b406d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE persons ADD COLUMN IF NOT EXISTS long_description TEXT")
    op.execute("ALTER TABLE persons ADD COLUMN IF NOT EXISTS links JSONB NOT NULL DEFAULT '[]'::jsonb")


def downgrade() -> None:
    op.execute("ALTER TABLE persons DROP COLUMN IF EXISTS links")
    op.execute("ALTER TABLE persons DROP COLUMN IF EXISTS long_description")
