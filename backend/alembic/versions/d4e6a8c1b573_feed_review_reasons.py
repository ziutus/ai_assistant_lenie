"""Move feed review reasons from a CHECK to an editable catalog.

Revision ID: d4e6a8c1b573
Revises: b9d3f1a7c526
"""

import sqlalchemy as sa
from alembic import op

revision = "d4e6a8c1b573"
down_revision = "b9d3f1a7c526"
branch_labels = None
depends_on = None

SEED_REASONS = [
    dict(code=code, label=label, sort_order=order, system=system, selectable=not system, active=True)
    for code, label, order, system in (
        ("not_interested", "Nie interesuje mnie temat", 10, False),
        ("duplicate", "Duplikat / już widziałem", 20, False),
        ("interesting_no_time", "Ciekawe, ale nie mam czasu", 25, False),
        ("already_known", "Już to znam", 30, False),
        ("too_long", "Za długie", 40, False),
        ("other", "Inny powód", 50, False),
        ("sent_to_radar", "Przeniesiono do radaru", 900, True),
        ("expired", "Wygasło (Może kiedyś)", 910, True),
    )
]
OLD_CHECK = (
    "review_reason IS NULL OR review_reason IN "
    "('not_interested','duplicate','already_known','too_long','other','sent_to_radar','expired')"
)


def upgrade():
    table = op.create_table(
        "feed_review_reasons",
        sa.Column("code", sa.String(40), primary_key=True),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("selectable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.bulk_insert(table, SEED_REASONS)
    op.drop_constraint("ck_feed_items_review_reason", "feed_items", type_="check")
    op.create_foreign_key(
        "fk_feed_items_review_reason",
        "feed_items",
        "feed_review_reasons",
        ["review_reason"],
        ["code"],
    )


def downgrade():
    op.drop_constraint("fk_feed_items_review_reason", "feed_items", type_="foreignkey")
    # Custom codes cannot survive the old CHECK; preserve the fact that a reason was recorded.
    op.execute("UPDATE feed_items SET review_reason = 'other' WHERE NOT (" + OLD_CHECK + ")")
    op.create_check_constraint("ck_feed_items_review_reason", "feed_items", OLD_CHECK)
    op.drop_table("feed_review_reasons")
