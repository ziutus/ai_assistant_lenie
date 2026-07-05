"""add text_extracted to web_documents

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-07-05 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # IF NOT EXISTS: the same column may already have been added by the Docker
    # init script 17-add-text-extracted-to-web-documents.sql on a fresh database.
    op.execute(
        "ALTER TABLE web_documents ADD COLUMN IF NOT EXISTS text_extracted TEXT"
    )


def downgrade() -> None:
    op.drop_column("web_documents", "text_extracted")
