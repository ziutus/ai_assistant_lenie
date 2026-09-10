"""Instrument document browsing and schedule daily audit retention."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b7e91a4c2d60"
down_revision = "6e93b4a80fc2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_browse_events",
        sa.Column("id", sa.BigInteger(), nullable=False, primary_key=True),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("browse_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("schema_version", sa.SmallInteger(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW() + INTERVAL '90 days'"),
        ),
        sa.Column("source_view", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=True),
        sa.Column("effective_query", sa.Text(), nullable=True),
        sa.Column("requested_mode", sa.Text(), nullable=False),
        sa.Column("execution_mode", sa.Text(), nullable=False),
        sa.Column("sort", sa.Text(), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("filters", postgresql.JSONB(), nullable=False),
        sa.Column("changed_fields", postgresql.JSONB(), nullable=False),
        sa.Column("criteria_origin", postgresql.JSONB(), nullable=False),
        sa.Column("page_size", sa.Integer(), nullable=False),
        sa.Column("offset", sa.Integer(), nullable=False),
        sa.Column("returned_count", sa.Integer(), nullable=True),
        sa.Column("total_count", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("has_more", sa.Boolean(), nullable=True),
        sa.Column(
            "interpretation_log_id",
            sa.BigInteger(),
            sa.ForeignKey("search_interpretation_logs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.CheckConstraint("source_view IN ('document_list', 'search')", name="ck_document_browse_events_source_view"),
        sa.CheckConstraint(
            "action IN ('initial_load','submit','filter_change','sort_change','page_change',"
            "'page_size_change','clear','refresh','correction')",
            name="ck_document_browse_events_action",
        ),
        sa.CheckConstraint(
            "outcome IN ('success','error','clarification_required')",
            name="ck_document_browse_events_outcome",
        ),
    )
    op.create_index("idx_document_browse_events_created", "document_browse_events", ["created_at"])
    op.create_index("idx_document_browse_events_expires", "document_browse_events", ["expires_at"])
    op.create_index(
        "idx_document_browse_events_source_created", "document_browse_events", ["source_view", "created_at"]
    )
    op.drop_constraint("ck_jobs_type", "jobs", type_="check")
    op.create_check_constraint(
        "ck_jobs_type",
        "jobs",
        "type IN ('feed_check','feed_check_all','feed_auto_import','feed_daily','content_group_suggest',"
        "'document_prepare','entity_enrichment','legacy_aws_pull','obsidian_reimport',"
        "'tool_candidate_detect','retention_sweep')",
    )
    op.execute("""
        INSERT INTO scheduled_tasks (id, enabled, timezone, times)
        VALUES ('retention_sweep', TRUE, 'Europe/Warsaw', '["03:30"]'::jsonb)
    """)


def downgrade() -> None:
    op.execute("DELETE FROM scheduled_tasks WHERE id = 'retention_sweep'")
    op.execute("DELETE FROM jobs WHERE type = 'retention_sweep'")
    op.drop_constraint("ck_jobs_type", "jobs", type_="check")
    op.create_check_constraint(
        "ck_jobs_type",
        "jobs",
        "type IN ('feed_check','feed_check_all','feed_auto_import','feed_daily','content_group_suggest',"
        "'document_prepare','entity_enrichment','legacy_aws_pull','obsidian_reimport','tool_candidate_detect')",
    )
    op.drop_table("document_browse_events")
