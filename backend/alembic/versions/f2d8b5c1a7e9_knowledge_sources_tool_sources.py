"""knowledge sources: course/newsletter fields on discovery_sources and the tool_sources link table

Revision ID: f2d8b5c1a7e9
Revises: e1c7a4b9d3f6
Create Date: 2026-10-23
"""

from alembic import op
import sqlalchemy as sa

revision = "f2d8b5c1a7e9"
down_revision = "e1c7a4b9d3f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("discovery_sources", sa.Column("kind", sa.String(30)))
    op.add_column("discovery_sources", sa.Column("status", sa.String(20)))
    op.add_column("discovery_sources", sa.Column("started_on", sa.Date))
    op.add_column("discovery_sources", sa.Column("finished_on", sa.Date))
    op.add_column("discovery_sources", sa.Column("rating", sa.SmallInteger))
    op.add_column("discovery_sources", sa.Column("review_note", sa.Text))
    op.add_column("discovery_sources", sa.Column("obsidian_note_path", sa.Text))
    op.create_check_constraint(
        "ck_discovery_sources_rating", "discovery_sources", "rating IS NULL OR rating BETWEEN 1 AND 5"
    )
    op.create_table(
        "tool_sources",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tool_id", sa.Integer, sa.ForeignKey("tools.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_id", sa.Integer, sa.ForeignKey("discovery_sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("context", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tool_id", "source_id", name="uq_tool_sources_tool_source"),
    )
    op.create_index("idx_tool_sources_source", "tool_sources", ["source_id"])


def downgrade() -> None:
    op.drop_index("idx_tool_sources_source", table_name="tool_sources")
    op.drop_table("tool_sources")
    op.drop_constraint("ck_discovery_sources_rating", "discovery_sources", type_="check")
    for column in ("obsidian_note_path", "review_note", "rating", "finished_on", "started_on", "status", "kind"):
        op.drop_column("discovery_sources", column)
