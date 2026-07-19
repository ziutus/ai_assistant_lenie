"""Add direct analysis-run attribution to LLM usage.

Revision ID: d1e2f3a4b5c6
Revises: c0d1e2f3a4b5
"""
from alembic import op
import sqlalchemy as sa

revision = "d1e2f3a4b5c6"
down_revision = "c0d1e2f3a4b5"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("llm_usage_logs", sa.Column("analysis_run_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_llm_usage_logs_analysis_run", "llm_usage_logs", "document_analysis_runs",
        ["analysis_run_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("idx_llm_usage_logs_analysis_run", "llm_usage_logs", ["analysis_run_id"])


def downgrade():
    op.drop_index("idx_llm_usage_logs_analysis_run", table_name="llm_usage_logs")
    op.drop_constraint("fk_llm_usage_logs_analysis_run", "llm_usage_logs", type_="foreignkey")
    op.drop_column("llm_usage_logs", "analysis_run_id")
