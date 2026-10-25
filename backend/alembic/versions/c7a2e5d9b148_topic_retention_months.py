"""Per-topic retention of feed items saved under "Może kiedyś"; review reason 'expired' for the automatic skip."""

import sqlalchemy as sa
from alembic import op

revision = "c7a2e5d9b148"
down_revision = "b4d8f2a6c915"
branch_labels = None
depends_on = None

OLD_REASONS = "'not_interested','duplicate','already_known','too_long','other','sent_to_radar'"
NEW_REASONS = OLD_REASONS + ",'expired'"


def _set_reasons(allowed: str) -> None:
    op.drop_constraint("ck_feed_items_review_reason", "feed_items", type_="check")
    op.create_check_constraint("ck_feed_items_review_reason", "feed_items", f"review_reason IS NULL OR review_reason IN ({allowed})")


def upgrade() -> None:
    op.add_column("content_groups", sa.Column("retention_months", sa.Integer))
    op.create_check_constraint(
        "ck_content_groups_retention_months", "content_groups",
        "retention_months IS NULL OR (kind = 'topic' AND retention_months BETWEEN 1 AND 120)",
    )
    _set_reasons(NEW_REASONS)


def downgrade() -> None:
    op.execute("UPDATE feed_items SET review_reason = 'other' WHERE review_reason = 'expired'")
    op.execute("UPDATE feed_review_decisions SET previous_review_reason = 'other' WHERE previous_review_reason = 'expired'")
    _set_reasons(OLD_REASONS)
    op.drop_constraint("ck_content_groups_retention_months", "content_groups", type_="check")
    op.drop_column("content_groups", "retention_months")
