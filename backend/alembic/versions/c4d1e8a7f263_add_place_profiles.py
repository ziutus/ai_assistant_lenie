"""Add place_profiles: cross-document Wikipedia link and aliases of a place."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c4d1e8a7f263"
down_revision = "7e3c9a1d4b82"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "place_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("canonical_name", sa.Text(), nullable=False),
        sa.Column("name_key", sa.Text(), nullable=False),
        sa.Column("wikipedia_url", sa.Text(), nullable=True),
        sa.Column("aliases", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("name_key", name="uq_place_profiles_name_key"),
    )


def downgrade():
    op.drop_table("place_profiles")
