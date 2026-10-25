"""Add ner_gazetteer_entries: database additions to curated NER gazetteer lists (ADR-029)."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "e8b3d6f2a417"
down_revision = "c4d1e8a7f263"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ner_gazetteer_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("name_pl", sa.Text(), nullable=False),
        sa.Column("patterns", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("geocode_alias", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("source_document_id", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "uq_ner_gazetteer_entries_kind_name",
        "ner_gazetteer_entries",
        ["kind", sa.text("lower(name_pl)")],
        unique=True,
    )


def downgrade():
    op.drop_index("uq_ner_gazetteer_entries_kind_name", table_name="ner_gazetteer_entries")
    op.drop_table("ner_gazetteer_entries")
