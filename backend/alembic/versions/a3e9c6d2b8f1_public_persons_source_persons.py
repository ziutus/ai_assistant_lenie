"""public persons (persons.kind/role/obsidian_note_path, source_persons) and tools.links

tools.links keeps the further pages a note names that have no field of their own (a second pricing
page, the Docker Hub page next to the homepage).

Revision ID: a3e9c6d2b8f1
Revises: f2d8b5c1a7e9
Create Date: 2026-10-23
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "a3e9c6d2b8f1"
down_revision = "f2d8b5c1a7e9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tools", sa.Column("links", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("persons", sa.Column("kind", sa.String(20)))
    op.add_column("persons", sa.Column("role", sa.String(100)))
    op.add_column("persons", sa.Column("obsidian_note_path", sa.Text))
    op.create_index("idx_persons_kind", "persons", ["kind"], postgresql_where=sa.text("kind IS NOT NULL"))
    op.create_table(
        "source_persons",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source_id", sa.Integer, sa.ForeignKey("discovery_sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("person_id", sa.Integer, sa.ForeignKey("persons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="author"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("source_id", "person_id", name="uq_source_persons_source_person"),
    )
    op.create_index("idx_source_persons_person", "source_persons", ["person_id"])


def downgrade() -> None:
    op.drop_index("idx_source_persons_person", table_name="source_persons")
    op.drop_table("source_persons")
    op.drop_index("idx_persons_kind", table_name="persons")
    for column in ("obsidian_note_path", "role", "kind"):
        op.drop_column("persons", column)
    op.drop_column("tools", "links")
