"""create document_removed_lines

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-07-05 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, None] = "b8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # IF NOT EXISTS: the same table may already have been created by the Docker
    # init script 18-create-document-removed-lines.sql on a fresh database.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS document_removed_lines (
            id          SERIAL PRIMARY KEY,
            document_id INTEGER NOT NULL REFERENCES web_documents(id) ON DELETE CASCADE,
            run_id      INTEGER REFERENCES document_analysis_runs(id) ON DELETE SET NULL,
            chunk_id    INTEGER REFERENCES document_chunks(id) ON DELETE SET NULL,
            source      VARCHAR(20) NOT NULL,
            line_text   TEXT NOT NULL,
            created_at  TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_removed_lines_document_id ON document_removed_lines(document_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_removed_lines_source ON document_removed_lines(source)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS document_removed_lines")
