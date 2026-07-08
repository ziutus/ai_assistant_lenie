"""create reader user tables (users, reading progress, document notes)

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-07-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d0e1f2a3b4c5"
down_revision: Union[str, None] = "c9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # IF NOT EXISTS: the same tables may already have been created by the Docker
    # init script 19-create-reader-user-tables.sql on a fresh database.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id           SERIAL PRIMARY KEY,
            username     VARCHAR(50) NOT NULL UNIQUE,
            display_name VARCHAR(100),
            created_at   TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_reading_progress (
            id                    SERIAL PRIMARY KEY,
            user_id               INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            document_id           INTEGER NOT NULL REFERENCES web_documents(id) ON DELETE CASCADE,
            current_chapter       INTEGER NOT NULL,
            current_chapter_title VARCHAR(500),
            read_chapters         INTEGER[] NOT NULL DEFAULT '{}',
            updated_at            TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_reading_progress_user_document UNIQUE (user_id, document_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_document_notes (
            id               SERIAL PRIMARY KEY,
            user_id          INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            document_id      INTEGER NOT NULL REFERENCES web_documents(id) ON DELETE CASCADE,
            chapter_position INTEGER,
            anchor_quote     TEXT NOT NULL,
            anchor_prefix    VARCHAR(100),
            anchor_suffix    VARCHAR(100),
            run_id           INTEGER REFERENCES document_analysis_runs(id) ON DELETE SET NULL,
            chunk_id         INTEGER REFERENCES document_chunks(id) ON DELETE SET NULL,
            note_text        TEXT NOT NULL,
            stance           VARCHAR(10),
            created_at       TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at       TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_notes_document_id ON user_document_notes(document_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_notes_user_id ON user_document_notes(user_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_document_notes")
    op.execute("DROP TABLE IF EXISTS user_reading_progress")
    op.execute("DROP TABLE IF EXISTS users")
