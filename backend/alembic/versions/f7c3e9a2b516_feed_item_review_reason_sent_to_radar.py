"""allow review reason 'sent_to_radar' on feed items

Revision ID: f7c3e9a2b516
Revises: e6b2d8f3a145
Create Date: 2026-10-23
"""

from alembic import op

revision = "f7c3e9a2b516"
down_revision = "e6b2d8f3a145"
branch_labels = None
depends_on = None

OLD = "review_reason IS NULL OR review_reason IN ('not_interested','duplicate','already_known','too_long','other')"
NEW = "review_reason IS NULL OR review_reason IN ('not_interested','duplicate','already_known','too_long','other','sent_to_radar')"


def upgrade() -> None:
    op.drop_constraint("ck_feed_items_review_reason", "feed_items", type_="check")
    op.create_check_constraint("ck_feed_items_review_reason", "feed_items", NEW)


def downgrade() -> None:
    op.execute("UPDATE feed_items SET review_reason = 'other' WHERE review_reason = 'sent_to_radar'")
    op.drop_constraint("ck_feed_items_review_reason", "feed_items", type_="check")
    op.create_check_constraint("ck_feed_items_review_reason", "feed_items", OLD)
