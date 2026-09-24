"""Add alternate and former contact names."""
from alembic import op
import sqlalchemy as sa

revision = "b7e29c4a8d10"
down_revision = "d3f7a1c9b8e2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "contact_alternate_names",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("contact_id", sa.Integer(), sa.ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("normalized_name", sa.Text(), nullable=False),
        sa.Column("name_kind", sa.String(20), nullable=False, server_default="former_name"),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("name_kind IN ('maiden_name', 'former_name', 'other')",
                           name="ck_contact_alternate_names_kind"),
    )
    op.create_index("idx_contact_alternate_names_contact", "contact_alternate_names", ["contact_id"])


def downgrade():
    op.drop_table("contact_alternate_names")
