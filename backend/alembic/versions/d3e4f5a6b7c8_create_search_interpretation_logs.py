"""create search interpretation audit log

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-07-18 18:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE search_interpretation_logs (
            id SERIAL PRIMARY KEY,
            raw_query TEXT NOT NULL,
            model VARCHAR(100),
            parser_version VARCHAR(50),
            prompt_version VARCHAR(50),
            raw_response TEXT,
            parsed_query JSONB,
            status VARCHAR(20) NOT NULL,
            error_code VARCHAR(50),
            error_message TEXT,
            fallback_used BOOLEAN NOT NULL DEFAULT FALSE,
            llm_latency_ms INTEGER,
            search_latency_ms INTEGER,
            result_count INTEGER,
            feedback_verdict VARCHAR(20),
            feedback_comment TEXT,
            corrected_query JSONB,
            feedback_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            expires_at TIMESTAMP NOT NULL DEFAULT (NOW() + INTERVAL '90 days'),
            CONSTRAINT ck_search_interpretation_logs_status CHECK (
                status IN ('parsed', 'ambiguous', 'invalid_json',
                           'validation_error', 'llm_error', 'fallback')
            ),
            CONSTRAINT ck_search_interpretation_logs_feedback CHECK (
                feedback_verdict IS NULL
                OR feedback_verdict IN ('correct', 'partially_correct', 'incorrect')
            )
        )
    """)
    op.execute("CREATE INDEX idx_search_interpretation_logs_created ON search_interpretation_logs(created_at)")
    op.execute(
        "CREATE INDEX idx_search_interpretation_logs_status_created ON search_interpretation_logs(status, created_at)"
    )
    op.execute("CREATE INDEX idx_search_interpretation_logs_expires ON search_interpretation_logs(expires_at)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS search_interpretation_logs")
