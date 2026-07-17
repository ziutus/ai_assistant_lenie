"""create document time periods

Revision ID: e9f0a1b2c3d4
Revises: d8e9f0a1b2c3
Create Date: 2026-07-17 20:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "e9f0a1b2c3d4"
down_revision: Union[str, None] = "d8e9f0a1b2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE document_time_periods (
            id SERIAL PRIMARY KEY,
            document_id INTEGER NOT NULL REFERENCES web_documents(id) ON DELETE CASCADE,
            chapter_position INTEGER,
            position INTEGER NOT NULL DEFAULT 0,
            period_label VARCHAR(100) NOT NULL,
            period_start_year INTEGER,
            period_end_year INTEGER,
            confidence VARCHAR(10) NOT NULL DEFAULT 'low',
            evidence TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_document_time_periods_confidence
                CHECK (confidence IN ('high', 'medium', 'low'))
        )
    """)
    op.execute(
        "CREATE INDEX idx_document_time_periods_document_chapter"
        " ON document_time_periods(document_id, chapter_position)"
    )
    op.execute(
        "CREATE INDEX idx_document_time_periods_years"
        " ON document_time_periods(period_start_year, period_end_year)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS document_time_periods")
