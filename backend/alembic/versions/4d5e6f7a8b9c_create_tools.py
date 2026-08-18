"""create tools table

Revision ID: 4d5e6f7a8b9c
Revises: 2b3c4d5e6f7a
Create Date: 2026-08-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "4d5e6f7a8b9c"
down_revision: Union[str, Sequence[str], None] = "2b3c4d5e6f7a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_table(
        "tools",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "uuid", sa.String(36), nullable=False, unique=True,
            server_default=sa.text("gen_random_uuid()::text"),
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category_tags", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("homepage_url", sa.Text),
        sa.Column("license", sa.String(100)),
        sa.Column("pricing", sa.Text),
        sa.Column("personal_notes", sa.Text),
        sa.Column("source_document_id", sa.Integer, sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("source_candidate_id", sa.Integer, sa.ForeignKey("tool_candidates.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(20), nullable=False, server_default="accepted"),
        sa.Column("obsidian_note_path", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.execute("CREATE INDEX idx_tools_name_trgm ON tools USING gin (name gin_trgm_ops)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_tools_name_trgm")
    op.drop_table("tools")
