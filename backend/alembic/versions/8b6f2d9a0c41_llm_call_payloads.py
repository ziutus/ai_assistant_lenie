"""Expiring LLM request/response audit.

Revision ID: 8b6f2d9a0c41
Revises: 1f312d5ec5a8
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "8b6f2d9a0c41"
down_revision = "1f312d5ec5a8"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "llm_call_payloads",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("usage_log_id", sa.BigInteger(), sa.ForeignKey("llm_usage_logs.id", ondelete="SET NULL")),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("operation", sa.String(100), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("system_prompt", sa.Text()),
        sa.Column("request_text", sa.Text()),
        sa.Column("response_text", sa.Text()),
        sa.Column("error", sa.Text()),
        sa.Column("request_extra", sa.JSON().with_variant(JSONB(), "postgresql")),
        sa.Column("request_truncated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("response_truncated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_llm_call_payloads_usage_log_id", "llm_call_payloads", ["usage_log_id"])
    op.create_index("ix_llm_call_payloads_document_created", "llm_call_payloads", ["document_id", "created_at"])
    op.create_index("ix_llm_call_payloads_created_at", "llm_call_payloads", ["created_at"])


def downgrade():
    op.drop_table("llm_call_payloads")
