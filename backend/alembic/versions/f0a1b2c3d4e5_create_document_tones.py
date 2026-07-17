"""create document tones

Revision ID: f0a1b2c3d4e5
Revises: e9f0a1b2c3d4
Create Date: 2026-07-18 00:30:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "f0a1b2c3d4e5"
down_revision: Union[str, None] = "e9f0a1b2c3d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE document_tones (
            id SERIAL PRIMARY KEY,
            document_id INTEGER NOT NULL REFERENCES web_documents(id) ON DELETE CASCADE,
            chapter_position INTEGER,
            emotion VARCHAR(20) NOT NULL,
            secondary_emotions VARCHAR(100),
            sentiment VARCHAR(10) NOT NULL,
            intensity VARCHAR(10) NOT NULL,
            registers VARCHAR(100),
            evidence TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_document_tones_sentiment
                CHECK (sentiment IN ('pozytywne', 'negatywne', 'neutralne', 'mieszane')),
            CONSTRAINT ck_document_tones_intensity
                CHECK (intensity IN ('niska', 'średnia', 'wysoka'))
        )
    """)
    op.execute(
        "CREATE INDEX idx_document_tones_document_chapter"
        " ON document_tones(document_id, chapter_position)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS document_tones")
