"""add structured reason to skipped feed items"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "f1e2d3c4b5a6"
down_revision: Union[str, tuple[str, str], None] = "b5c6d7e8f9a0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("feed_items", sa.Column("review_reason", sa.String(40), nullable=True))
    op.create_check_constraint(
        "ck_feed_items_review_reason",
        "feed_items",
        "review_reason IS NULL OR review_reason IN ('not_interested','duplicate','already_known','too_long','other')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_feed_items_review_reason", "feed_items", type_="check")
    op.drop_column("feed_items", "review_reason")
