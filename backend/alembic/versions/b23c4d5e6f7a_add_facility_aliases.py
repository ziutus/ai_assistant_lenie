"""Add aliases for facility mention matching.

Revision ID: b23c4d5e6f7a
Revises: a12b3c4d5e6f
Create Date: 2026-08-20 00:00:00.000000
"""

from alembic import op


revision = "b23c4d5e6f7a"
down_revision = "a12b3c4d5e6f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE facilities ADD COLUMN aliases JSONB NOT NULL DEFAULT '[]'::jsonb")
    # Both the noun form and its form used in the article's question are
    # legitimate mentions of the same plant.
    op.execute("""
        UPDATE facilities
        SET aliases = '["elektrownia Gravelines", "elektrowni Gravelines"]'::jsonb,
            updated_at = NOW()
        WHERE wikidata_qid = 'Q1739407'
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE facilities DROP COLUMN aliases")
