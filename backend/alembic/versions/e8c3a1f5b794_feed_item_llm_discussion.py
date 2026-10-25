"""Independent discussion queue for feed items."""

from alembic import op
import sqlalchemy as sa

revision = "e8c3a1f5b794"
down_revision = "d2f8b4a1c693"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("feed_items", sa.Column("llm_discussion_status", sa.String(10), nullable=True))
    op.add_column("feed_items", sa.Column("llm_discussion_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("feed_items", sa.Column("llm_discussion_done_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("feed_items", sa.Column("llm_discussion_result", sa.Text(), nullable=True))
    op.create_check_constraint("ck_feed_items_llm_discussion_status", "feed_items",
                               "llm_discussion_status IS NULL OR llm_discussion_status IN ('open','done')")
    op.create_index("idx_feed_items_llm_discussion", "feed_items", ["llm_discussion_status", "llm_discussion_at"],
                    postgresql_where=sa.text("llm_discussion_status IS NOT NULL"))


def downgrade() -> None:
    op.drop_index("idx_feed_items_llm_discussion", table_name="feed_items")
    op.drop_constraint("ck_feed_items_llm_discussion_status", "feed_items", type_="check")
    for column in ("llm_discussion_result", "llm_discussion_done_at", "llm_discussion_at", "llm_discussion_status"):
        op.drop_column("feed_items", column)
