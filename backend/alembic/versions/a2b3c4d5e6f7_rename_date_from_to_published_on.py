"""rename date_from to published_on and date_from_source to published_on_method

Stage 11a of docs/search-rebuild-implementation-plan.md: physical column rename
only — types, values and CHECK semantics stay identical.

Revision ID: a2b3c4d5e6f7
Revises: f5a6b7c8d9e0
Create Date: 2026-07-19 02:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, None] = "f5a6b7c8d9e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE web_documents RENAME COLUMN date_from TO published_on")
    op.execute("ALTER TABLE web_documents RENAME COLUMN date_from_source TO published_on_method")
    op.execute("ALTER INDEX idx_web_documents_date_from RENAME TO idx_web_documents_published_on")
    op.execute(
        "ALTER TABLE web_documents RENAME CONSTRAINT ck_web_documents_date_from_source"
        " TO ck_web_documents_published_on_method"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE web_documents RENAME CONSTRAINT ck_web_documents_published_on_method"
        " TO ck_web_documents_date_from_source"
    )
    op.execute("ALTER INDEX idx_web_documents_published_on RENAME TO idx_web_documents_date_from")
    op.execute("ALTER TABLE web_documents RENAME COLUMN published_on_method TO date_from_source")
    op.execute("ALTER TABLE web_documents RENAME COLUMN published_on TO date_from")
