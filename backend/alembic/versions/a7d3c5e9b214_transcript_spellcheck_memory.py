"""Memory of the reviewer's decisions in the transcript spellcheck panel.

An accepted pair (word -> approved spelling) is offered again, without a model call, for the same channel; a
rejected word ("this is a term, not a slip") is skipped without a model call. ``document_ids`` lists the distinct
documents that confirmed an accepted pair, which is what makes it trusted.

Revision ID: a7d3c5e9b214
Revises: f6b1a9c4d7e2
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "a7d3c5e9b214"
down_revision = "f6b1a9c4d7e2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "transcript_spellcheck_memory",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("author_key", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("original_key", sa.Text(), nullable=False),
        sa.Column("original", sa.Text(), nullable=False),
        sa.Column("replacement", sa.Text()),
        sa.Column("replacement_key", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("decision", sa.String(length=10), nullable=False),
        sa.Column("document_ids", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("times", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("decision IN ('accepted', 'rejected')", name="ck_transcript_spellcheck_memory_decision"),
    )
    op.create_index("uq_transcript_spellcheck_memory_key", "transcript_spellcheck_memory",
                    ["author_key", "original_key", "decision", "replacement_key"], unique=True)
    op.create_index("ix_transcript_spellcheck_memory_original", "transcript_spellcheck_memory", ["original_key"])


def downgrade():
    op.drop_index("ix_transcript_spellcheck_memory_original", table_name="transcript_spellcheck_memory")
    op.drop_index("uq_transcript_spellcheck_memory_key", table_name="transcript_spellcheck_memory")
    op.drop_table("transcript_spellcheck_memory")
