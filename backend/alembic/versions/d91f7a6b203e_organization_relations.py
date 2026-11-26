"""Company shareholder evidence, including historical periods.

Revision ID: d91f7a6b203e
Revises: c82e6f904ab1
"""
from alembic import op
import sqlalchemy as sa

revision = "d91f7a6b203e"
down_revision = "c82e6f904ab1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "organization_relations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("person_id", sa.Integer(), sa.ForeignKey("persons.id", ondelete="SET NULL")),
        sa.Column("related_organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="SET NULL")),
        sa.Column("link_rejected", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("subject_name", sa.Text(), nullable=False),
        sa.Column("subject_krs", sa.String(10)),
        sa.Column("subject_key", sa.Text(), nullable=False),
        sa.Column("role", sa.String(30), nullable=False),
        sa.Column("details", sa.Text()),
        sa.Column("valid_from", sa.Date()),
        sa.Column("valid_to", sa.Date()),
        sa.Column("source", sa.String(10), nullable=False),
        sa.Column("source_url", sa.Text()),
        sa.Column("checked_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    for column in ("organization_id", "related_organization_id", "subject_krs"):
        op.create_index(f"ix_organization_relations_{column}", "organization_relations", [column])
    columns = ["organization_id", "role", "source", "subject_key"]
    for name, fields, condition in (
        ("dated", columns + ["valid_from"], "valid_from IS NOT NULL"),
        ("undated", columns, "valid_from IS NULL"),
    ):
        op.create_index(f"uq_org_relation_{name}", "organization_relations", fields, unique=True,
                        postgresql_where=sa.text(condition), sqlite_where=sa.text(condition))


def downgrade():
    op.drop_table("organization_relations")
