"""create document_references

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
Create Date: 2026-07-11 00:00:00.000000

Footnotes/references extracted out of a book's text_md
(library/references.py): OCR-ed books carry footnote lines inline where they
fell on the scanned page — they interrupt reading and pollute NER/embeddings
(footnote URLs used to become person entities). Extraction moves them here;
the reader renders them as a per-chapter "Przypisy" section.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "f8a9b0c1d2e3"
down_revision: Union[str, None] = "e7f8a9b0c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "document_references",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "document_id", sa.Integer(),
            sa.ForeignKey("web_documents.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("chapter_position", sa.Integer()),
        sa.Column("marker", sa.String(length=10), nullable=False),
        sa.Column("ref_text", sa.Text(), nullable=False),
        sa.Column("url", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_document_references_document_id", "document_references", ["document_id"])


def downgrade() -> None:
    op.drop_index("idx_document_references_document_id", table_name="document_references")
    op.drop_table("document_references")
