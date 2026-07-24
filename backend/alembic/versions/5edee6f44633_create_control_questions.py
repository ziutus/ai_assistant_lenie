"""create control_questions and document_control_answers

Revision ID: 5edee6f44633
Revises: f35c4d5e6a7b
Create Date: 2026-07-24 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "5edee6f44633"
down_revision: Union[str, None] = "f35c4d5e6a7b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE control_questions (
            id SERIAL PRIMARY KEY,
            source_file VARCHAR(255) NOT NULL,
            section_header TEXT NOT NULL,
            body TEXT,
            tags VARCHAR(255),
            position INTEGER NOT NULL DEFAULT 0,
            active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX idx_control_questions_source_file ON control_questions(source_file)"
    )
    op.execute("""
        CREATE TABLE document_control_answers (
            id SERIAL PRIMARY KEY,
            document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            chapter_position INTEGER,
            question_id INTEGER REFERENCES control_questions(id) ON DELETE SET NULL,
            question_header TEXT NOT NULL,
            tags VARCHAR(255),
            answer_summary TEXT NOT NULL,
            evidence TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX idx_document_control_answers_document_chapter"
        " ON document_control_answers(document_id, chapter_position)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS document_control_answers")
    op.execute("DROP TABLE IF EXISTS control_questions")
