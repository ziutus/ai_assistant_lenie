"""create document_tone_spans and document_tones.core_tone

Passages of a document that stand out from the tone of their chapter (a malicious remark, irony) or carry the
substance whatever the tone ("kluczowy"), found on request by library/tone_spans.py, plus the chapter's tone
recomputed without the outlier passages.

Revision ID: 7d2e9b4f1a63
Revises: 8b6f2d9a0c41
Create Date: 2026-11-06 13:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "7d2e9b4f1a63"
down_revision: Union[str, None] = "8b6f2d9a0c41"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE document_tone_spans (
            id SERIAL PRIMARY KEY,
            document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            chapter_position INTEGER,
            role VARCHAR(10) NOT NULL,
            label VARCHAR(30) NOT NULL,
            quote TEXT NOT NULL,
            note TEXT,
            importance SMALLINT,
            status VARCHAR(10) NOT NULL DEFAULT 'proposed',
            model VARCHAR(120),
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_document_tone_spans_role CHECK (role IN ('outlier', 'key')),
            CONSTRAINT ck_document_tone_spans_status CHECK (status IN ('proposed', 'confirmed', 'rejected')),
            CONSTRAINT ck_document_tone_spans_importance CHECK (importance IS NULL OR importance BETWEEN 1 AND 3)
        )
    """)
    op.execute(
        "CREATE INDEX idx_document_tone_spans_document_chapter"
        " ON document_tone_spans(document_id, chapter_position)"
    )
    op.execute("ALTER TABLE document_tones ADD COLUMN IF NOT EXISTS core_tone JSONB")


def downgrade() -> None:
    op.execute("ALTER TABLE document_tones DROP COLUMN IF EXISTS core_tone")
    op.execute("DROP TABLE IF EXISTS document_tone_spans")
