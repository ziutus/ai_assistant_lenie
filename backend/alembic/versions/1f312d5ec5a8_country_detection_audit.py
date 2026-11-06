"""Audit country tag detection.

Revision ID: 1f312d5ec5a8
Revises: a4c8e2f6b913
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "1f312d5ec5a8"
down_revision = "a4c8e2f6b913"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "country_detection_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("analysis_run_id", sa.BigInteger()),
        sa.Column("trigger", sa.String(30), nullable=False),
        sa.Column("text_source", sa.String(20), nullable=False),
        sa.Column("text_chars", sa.Integer(), nullable=False),
        sa.Column("threshold", sa.Integer(), nullable=False),
        sa.Column("llm_called", sa.Boolean(), nullable=False),
        sa.Column("llm_model", sa.String(100)),
        sa.Column("llm_prompt", sa.Text()),
        sa.Column("llm_response", sa.Text()),
        sa.Column("llm_usage_log_id", sa.BigInteger()),
        sa.Column("llm_error", sa.Text()),
        sa.Column("tags_before", sa.Text()),
        sa.Column("tags_added", sa.JSON().with_variant(JSONB(), "postgresql"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_country_detection_runs_document_created", "country_detection_runs", ["document_id", "created_at"])
    op.create_table(
        "country_tag_decisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("detection_run_id", sa.Integer(),
                  sa.ForeignKey("country_detection_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("country_slug", sa.String(60), nullable=False),
        sa.Column("country_name", sa.String(100), nullable=False),
        sa.Column("mention_count", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(30), nullable=False),
        sa.Column("snippets", sa.JSON().with_variant(JSONB(), "postgresql")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_country_tag_decisions_detection_run_id", "country_tag_decisions", ["detection_run_id"])


def downgrade():
    op.drop_table("country_tag_decisions")
    op.drop_table("country_detection_runs")
