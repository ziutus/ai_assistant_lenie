"""Audit table of what stored transcript correction rules changed in a document.

The corrected transcript no longer contains the original wording, so without this table the reader cannot be
told which words a region/channel dictionary repaired (the "Słownik regionu" panel on /ner/:id).

Revision ID: d2b7e4a9c351
Revises: c9d4a7e2b158
"""

from alembic import op
import sqlalchemy as sa

revision = "d2b7e4a9c351"
down_revision = "c9d4a7e2b158"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "transcript_correction_applications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rule_id", sa.Integer(), sa.ForeignKey("transcript_corrections.id", ondelete="SET NULL")),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("replacement_text", sa.Text(), nullable=False),
        sa.Column("chapter_position", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("occurrences", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("applied_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_transcript_correction_applications_document", "transcript_correction_applications",
                    ["document_id"])


def downgrade():
    op.drop_index("ix_transcript_correction_applications_document",
                  table_name="transcript_correction_applications")
    op.drop_table("transcript_correction_applications")
