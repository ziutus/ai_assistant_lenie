"""Tie persons to countries and geopolitical macro-regions.

Organizations already have `organization_countries`; a person had no territory at all, so a Yemen document could not
prefer "al-Nuzajli" or "Salih" over a namesake, and an ASR-mangled name could not be matched against the people of
the document's country. `kind` = country (slug of the kraj-<slug> tag) or region (slug of the miejsce-<slug> tag of a
macro-region such as Bliski Wschód); the optional dates bound a role.

Revision ID: e5c9a1d3b742
Revises: d2b7e4a9c351
"""

from alembic import op
import sqlalchemy as sa

revision = "e5c9a1d3b742"
down_revision = "d2b7e4a9c351"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "person_territories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("person_id", sa.Integer(), sa.ForeignKey("persons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("relation", sa.String(20), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("valid_from", sa.Date()),
        sa.Column("valid_to", sa.Date()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("person_id", "kind", "slug", "relation", name="uq_person_territories_tie"),
        sa.CheckConstraint("kind IN ('country', 'region')", name="ck_person_territories_kind"),
    )
    op.create_index("ix_person_territories_territory", "person_territories", ["kind", "slug"])


def downgrade():
    op.drop_index("ix_person_territories_territory", table_name="person_territories")
    op.drop_table("person_territories")
