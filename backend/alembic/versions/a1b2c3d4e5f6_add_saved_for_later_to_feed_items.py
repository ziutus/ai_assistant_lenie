"""add saved-for-later state to feed items"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "b5c6d7e8f9a0"
down_revision: Union[str, tuple[str, str], None] = "f9a0b1c2d3e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_STATUS_CHECK = "status IN ('new','llm_analysis_requested','saved_for_later','imported','skipped','ignored','error')"
OLD_STATUS_CHECK = "status IN ('new','llm_analysis_requested','imported','skipped','ignored','error')"


def upgrade() -> None:
    op.add_column("feed_items", sa.Column("saved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("feed_items", sa.Column("saved_by_user_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_feed_items_saved_by_user_id", "feed_items", "users", ["saved_by_user_id"], ["id"], ondelete="SET NULL")
    op.drop_constraint("ck_feed_items_status", "feed_items", type_="check")
    op.create_check_constraint("ck_feed_items_status", "feed_items", NEW_STATUS_CHECK)
    op.create_index("idx_feed_items_status_saved_at", "feed_items", ["status", "saved_at"])


def downgrade() -> None:
    op.execute("UPDATE feed_items SET status = 'new' WHERE status = 'saved_for_later'")
    op.drop_index("idx_feed_items_status_saved_at", table_name="feed_items")
    op.drop_constraint("ck_feed_items_status", "feed_items", type_="check")
    op.create_check_constraint("ck_feed_items_status", "feed_items", OLD_STATUS_CHECK)
    op.drop_constraint("fk_feed_items_saved_by_user_id", "feed_items", type_="foreignkey")
    op.drop_column("feed_items", "saved_by_user_id")
    op.drop_column("feed_items", "saved_at")
