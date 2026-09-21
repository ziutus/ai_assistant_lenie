"""Remember rejected duplicate suggestions independently of query ordering.

Canonical pairs prevent repeated suggestions after swapping the two contacts.
Create Date: 2026-09-21
"""
from alembic import op
import sqlalchemy as sa

revision = "a9c7e2d48f10"
down_revision = "164fd8a6b359"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "contact_duplicate_dismissals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("contact_id_a", sa.Integer(), sa.ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contact_id_b", sa.Integer(), sa.ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("contact_id_a < contact_id_b", name="ck_contact_duplicate_dismissals_order"),
        sa.UniqueConstraint("contact_id_a", "contact_id_b"),
    )
    op.create_index("idx_contact_duplicate_dismissals_a", "contact_duplicate_dismissals", ["contact_id_a"])
    op.create_index("idx_contact_duplicate_dismissals_b", "contact_duplicate_dismissals", ["contact_id_b"])


def downgrade():
    op.drop_table("contact_duplicate_dismissals")
