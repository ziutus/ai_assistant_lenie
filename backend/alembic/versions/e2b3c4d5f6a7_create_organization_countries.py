"""Create organization_countries (countries an organization is based in / operates in / linked to).

Revision ID: e2b3c4d5f6a7
Revises: d1a2b3c4e5f6
"""

from alembic import op
import sqlalchemy as sa

revision = "e2b3c4d5f6a7"
down_revision = "d1a2b3c4e5f6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "organization_countries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("country_slug", sa.String(80), nullable=False),
        sa.Column("relation", sa.String(20), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "country_slug", "relation"),
    )
    op.create_index("ix_organization_countries_organization_id", "organization_countries", ["organization_id"])


def downgrade():
    op.drop_index("ix_organization_countries_organization_id", table_name="organization_countries")
    op.drop_table("organization_countries")
