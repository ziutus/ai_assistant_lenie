"""add html to published_on_method check constraint

Revision ID: 2a9042961f41
Revises: a1b2c3d4e5f7
Create Date: 2026-08-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2a9042961f41"
down_revision: Union[str, None] = "a1b2c3d4e5f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # "html" — published_on resolved deterministically from the page's own
    # structured metadata (JSON-LD datePublished / <meta> tags,
    # library.article_metadata.extract_article_publication_date), distinct
    # from "llm" (extract_publication_date_info), "relative" (relative-date
    # artifact resolved against ingested_at) and "manual" (reviewer-typed).
    # POST /document/<id>/extract_publication_date has set this method since
    # its deterministic HTML path was added (ck_documents_byline_method
    # already allows the equivalent 'html' value for byline_method), but this
    # constraint was never updated to match — every save through that path
    # failed with a CheckViolation (surfaced verifying gazeta.pl doc 9376:
    # datePublished was correctly extracted from JSON-LD but could not be
    # persisted).
    op.execute("ALTER TABLE documents DROP CONSTRAINT IF EXISTS ck_documents_published_on_method")
    op.execute("""
        ALTER TABLE documents ADD CONSTRAINT ck_documents_published_on_method
        CHECK (published_on_method IS NULL OR published_on_method IN ('manual', 'llm', 'relative', 'html'))
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE documents DROP CONSTRAINT IF EXISTS ck_documents_published_on_method")
    op.execute("""
        ALTER TABLE documents ADD CONSTRAINT ck_documents_published_on_method
        CHECK (published_on_method IS NULL OR published_on_method IN ('manual', 'llm', 'relative'))
    """)
