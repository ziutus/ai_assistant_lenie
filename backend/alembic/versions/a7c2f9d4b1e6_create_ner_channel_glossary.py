"""Add ner_channel_glossary and ner_glossary_applications: per-channel STT name glossary for NER."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "a7c2f9d4b1e6"
down_revision = "e8b3d6f2a417"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ner_channel_glossary",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("author", sa.Text(), nullable=False),
        sa.Column("canonical_name", sa.Text(), nullable=False),
        sa.Column("aliases", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("fuzzy", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "uq_ner_channel_glossary_author_name",
        "ner_channel_glossary",
        [sa.text("lower(author)"), sa.text("lower(canonical_name)")],
        unique=True,
    )
    op.create_table(
        "ner_glossary_applications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("glossary_id", sa.Integer(), sa.ForeignKey("ner_channel_glossary.id", ondelete="SET NULL")),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("replacement_text", sa.Text(), nullable=False),
        sa.Column("occurrences", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("applied_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_ner_glossary_applications_document_id", "ner_glossary_applications", ["document_id"])


def downgrade():
    op.drop_index("ix_ner_glossary_applications_document_id", table_name="ner_glossary_applications")
    op.drop_table("ner_glossary_applications")
    op.drop_index("uq_ner_channel_glossary_author_name", table_name="ner_channel_glossary")
    op.drop_table("ner_channel_glossary")
