"""create persistent document analysis jobs

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-07-17 16:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "d8e9f0a1b2c3"
down_revision: Union[str, None] = "c7d8e9f0a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE document_analysis_jobs (
            id VARCHAR(32) PRIMARY KEY,
            document_id INTEGER NOT NULL REFERENCES web_documents(id) ON DELETE CASCADE,
            run_id INTEGER REFERENCES document_analysis_runs(id) ON DELETE SET NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'queued',
            parameters JSONB NOT NULL,
            progress TEXT,
            error TEXT,
            chunk_count INTEGER,
            ad_count INTEGER,
            topic_section_count INTEGER,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            started_at TIMESTAMP,
            finished_at TIMESTAMP,
            CONSTRAINT ck_document_analysis_jobs_status
                CHECK (status IN ('queued', 'running', 'done', 'failed'))
        )
    """)
    op.execute("CREATE INDEX idx_document_analysis_jobs_document_created ON document_analysis_jobs(document_id, created_at)")
    op.execute("CREATE INDEX idx_document_analysis_jobs_status_created ON document_analysis_jobs(status, created_at)")
    op.execute("""
        CREATE UNIQUE INDEX uq_document_analysis_jobs_active_document
        ON document_analysis_jobs(document_id)
        WHERE status IN ('queued', 'running')
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS document_analysis_jobs")
