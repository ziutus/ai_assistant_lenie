"""rename author to byline and author_source to byline_method

Stage 11b of docs/search-rebuild-implementation-plan.md: physical column rename
only — types, values and CHECK semantics stay identical. The relational author
model (document_persons role='author') and ner_exclusions.author are untouched;
byline is the presentational display cache on the document row.

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-07-19 02:30:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, None] = "a2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE web_documents RENAME COLUMN author TO byline")
    op.execute("ALTER TABLE web_documents RENAME COLUMN author_source TO byline_method")
    op.execute(
        "ALTER TABLE web_documents RENAME CONSTRAINT ck_web_documents_author_source"
        " TO ck_web_documents_byline_method"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE web_documents RENAME CONSTRAINT ck_web_documents_byline_method"
        " TO ck_web_documents_author_source"
    )
    op.execute("ALTER TABLE web_documents RENAME COLUMN byline_method TO author_source")
    op.execute("ALTER TABLE web_documents RENAME COLUMN byline TO author")
