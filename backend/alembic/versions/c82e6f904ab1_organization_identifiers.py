"""Human-entered organization registry identifiers.

Revision ID: c82e6f904ab1
Revises: a7d3c5e9b214
"""
from alembic import op
import sqlalchemy as sa

revision = "c82e6f904ab1"
down_revision = "a7d3c5e9b214"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "organization_identifiers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("country_code", sa.String(2), nullable=False),
        sa.Column("identifier_type", sa.String(30), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text()),
        sa.Column("note", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("country_code", "identifier_type", "value", name="uq_organization_identifiers_number"),
    )
    op.create_index("ix_organization_identifiers_organization_id", "organization_identifiers", ["organization_id"])


def downgrade():
    op.drop_table("organization_identifiers")
