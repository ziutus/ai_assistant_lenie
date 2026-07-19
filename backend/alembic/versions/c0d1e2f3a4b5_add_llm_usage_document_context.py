"""add document and analysis job context to LLM usage

Revision ID: c0d1e2f3a4b5
Revises: b9c0d1e2f3a4
"""
from alembic import op

revision = "c0d1e2f3a4b5"
down_revision = "b9c0d1e2f3a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE llm_usage_logs ADD COLUMN document_id INTEGER REFERENCES documents(id) ON DELETE SET NULL")
    op.execute("ALTER TABLE llm_usage_logs ADD COLUMN analysis_job_id VARCHAR(32) REFERENCES document_analysis_jobs(id) ON DELETE SET NULL")
    op.execute("CREATE INDEX idx_llm_usage_logs_document_called ON llm_usage_logs(document_id, called_at)")
    op.execute("CREATE INDEX idx_llm_usage_logs_analysis_job ON llm_usage_logs(analysis_job_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_llm_usage_logs_analysis_job")
    op.execute("DROP INDEX IF EXISTS idx_llm_usage_logs_document_called")
    op.execute("ALTER TABLE llm_usage_logs DROP COLUMN analysis_job_id")
    op.execute("ALTER TABLE llm_usage_logs DROP COLUMN document_id")
