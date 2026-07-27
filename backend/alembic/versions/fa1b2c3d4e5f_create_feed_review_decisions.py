"""store feed curation decisions for audit, learning and undo"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "fa1b2c3d4e5f"
down_revision: Union[str, Sequence[str], None] = "f1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feed_review_decisions",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("batch_id", sa.String(32), nullable=False),
        sa.Column("job_id", sa.String(32), nullable=True),
        sa.Column("feed_item_id", sa.Integer, sa.ForeignKey("feed_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("previous_status", sa.String(40), nullable=False),
        sa.Column("new_status", sa.String(40), nullable=False),
        sa.Column("previous_document_id", sa.Integer, sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("new_document_id", sa.Integer, sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("previous_saved_at", sa.DateTime(timezone=True)),
        sa.Column("previous_review_reason", sa.String(40)),
        sa.Column("previous_ignored_pattern", sa.Text),
        sa.Column("previous_group_ids", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("new_group_ids", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("undone_at", sa.DateTime(timezone=True)),
        sa.Column("undone_by_user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL")),
    )
    op.create_index("idx_feed_review_decisions_batch", "feed_review_decisions", ["batch_id", "created_at"])
    op.create_index("idx_feed_review_decisions_job", "feed_review_decisions", ["job_id", "created_at"])
    op.create_index("idx_feed_review_decisions_item", "feed_review_decisions", ["feed_item_id", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_feed_review_decisions_item", table_name="feed_review_decisions")
    op.drop_index("idx_feed_review_decisions_job", table_name="feed_review_decisions")
    op.drop_index("idx_feed_review_decisions_batch", table_name="feed_review_decisions")
    op.drop_table("feed_review_decisions")
