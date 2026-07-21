"""add relative to published_on_method check constraint

Revision ID: c07c2d94a19f
Revises: c8d9eafb0c1d
Create Date: 2026-07-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c07c2d94a19f"
down_revision: Union[str, None] = "c8d9eafb0c1d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # "relative" — published_on resolved deterministically from a relative-date
    # artifact ("Wczoraj, HH:MM", "X minut/godzin temu") against ingested_at
    # (library.article_cleaner.resolve_relative_publication_date), distinct
    # from "llm" (extract_publication_date_info) and "manual" (reviewer-typed).
    op.execute("ALTER TABLE documents DROP CONSTRAINT IF EXISTS ck_documents_published_on_method")
    op.execute("""
        ALTER TABLE documents ADD CONSTRAINT ck_documents_published_on_method
        CHECK (published_on_method IS NULL OR published_on_method IN ('manual', 'llm', 'relative'))
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE documents DROP CONSTRAINT IF EXISTS ck_documents_published_on_method")
    op.execute("""
        ALTER TABLE documents ADD CONSTRAINT ck_documents_published_on_method
        CHECK (published_on_method IS NULL OR published_on_method IN ('manual', 'llm'))
    """)
