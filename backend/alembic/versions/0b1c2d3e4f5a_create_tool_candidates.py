"""create tool_candidates table"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0b1c2d3e4f5a"
down_revision: Union[str, Sequence[str], None] = "868602adab5b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tool_candidates",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("source_document_id", sa.Integer, sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("context_snippet", sa.Text),
        sa.Column("detected_by", sa.String(50), nullable=False, server_default="bielik"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('pending', 'accepted', 'rejected', 'deferred')", name="ck_tool_candidates_status"),
    )
    op.create_index("idx_tool_candidates_source_status", "tool_candidates", ["source_document_id", "status"])


def downgrade() -> None:
    op.drop_index("idx_tool_candidates_source_status", table_name="tool_candidates")
    op.drop_table("tool_candidates")
