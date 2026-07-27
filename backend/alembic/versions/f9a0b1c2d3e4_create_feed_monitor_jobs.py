"""create persistent feed monitor, LLM analysis and generic job tables"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "f9a0b1c2d3e4"
down_revision: Union[str, tuple[str, str], None] = ("b7e2f19c4a05", "f8a9b0c1d2e3")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("INSERT INTO processing_status_types (name) VALUES ('NEED_LLM_ANALYSIS') ON CONFLICT (name) DO NOTHING")
    op.create_table("feed_sources",
        sa.Column("id", sa.Integer, primary_key=True), sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("type", sa.String(30), nullable=False), sa.Column("url", sa.Text), sa.Column("channel_id", sa.String(128)),
        sa.Column("language", sa.String(10), nullable=False, server_default="pl"),
        sa.Column("collection_id", sa.Integer, sa.ForeignKey("collections.id", ondelete="SET NULL")),
        sa.Column("tags", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")), sa.Column("auto_import", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("disabled", sa.Boolean, nullable=False, server_default=sa.false()), sa.Column("auto_import_after", sa.DateTime(timezone=True)),
        sa.Column("discovery_source_id", sa.Integer, sa.ForeignKey("discovery_sources.id", ondelete="SET NULL")),
        sa.Column("default_state", sa.String(50), nullable=False, server_default="URL_ADDED"), sa.Column("field_mapping", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("skip_url_patterns", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")), sa.Column("skip_title_patterns", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("last_checked_at", sa.DateTime(timezone=True)), sa.Column("last_successful_import_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_at", sa.DateTime(timezone=True)), sa.Column("last_error", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("type IN ('rss','wordpress','youtube_channel','json_api')", name="ck_feed_sources_type"),
        sa.CheckConstraint("(type = 'youtube_channel' AND channel_id IS NOT NULL) OR (type <> 'youtube_channel' AND url IS NOT NULL)", name="ck_feed_sources_endpoint"),
        sa.ForeignKeyConstraint(["default_state"], ["processing_status_types.name"]),
    )
    op.create_table("feed_items",
        sa.Column("id", sa.Integer, primary_key=True), sa.Column("feed_source_id", sa.Integer, sa.ForeignKey("feed_sources.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("url", sa.Text, nullable=False), sa.Column("canonical_url", sa.Text, nullable=False), sa.Column("title", sa.Text, nullable=False, server_default=""), sa.Column("summary", sa.Text),
        sa.Column("published_at", sa.DateTime(timezone=True)), sa.Column("raw_payload", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(40), nullable=False, server_default="new"), sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)), sa.Column("reviewed_by_user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL")), sa.Column("document_id", sa.Integer, sa.ForeignKey("documents.id", ondelete="SET NULL")), sa.Column("review_note", sa.Text), sa.Column("ignored_pattern", sa.Text), sa.Column("last_error", sa.Text),
        sa.UniqueConstraint("feed_source_id", "canonical_url", name="uq_feed_items_source_canonical"),
        sa.CheckConstraint("status IN ('new','llm_analysis_requested','imported','skipped','ignored','error')", name="ck_feed_items_status"),
    )
    op.create_index("idx_feed_items_source_status", "feed_items", ["feed_source_id", "status"])
    op.create_index("idx_feed_items_status_first_seen", "feed_items", ["status", "first_seen_at"])
    op.create_table("jobs",
        sa.Column("id", sa.String(32), primary_key=True), sa.Column("type", sa.String(40), nullable=False), sa.Column("status", sa.String(30), nullable=False, server_default="queued"),
        sa.Column("parameters", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")), sa.Column("progress", postgresql.JSONB), sa.Column("result", postgresql.JSONB), sa.Column("error", sa.Text), sa.Column("attempt", sa.Integer, nullable=False, server_default="0"), sa.Column("max_attempts", sa.Integer, nullable=False, server_default="3"), sa.Column("available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("started_at", sa.DateTime(timezone=True)), sa.Column("heartbeat_at", sa.DateTime(timezone=True)), sa.Column("finished_at", sa.DateTime(timezone=True)), sa.Column("initiated_by_user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL")), sa.Column("idempotency_key", sa.String(255), unique=True),
        sa.CheckConstraint("type IN ('feed_check','feed_check_all','feed_auto_import','feed_daily')", name="ck_jobs_type"), sa.CheckConstraint("status IN ('queued','running','done','failed','cancel_requested','cancelled')", name="ck_jobs_status"), sa.CheckConstraint("attempt >= 0 AND max_attempts >= 0", name="ck_jobs_attempts"),
    )
    op.create_table("feed_item_llm_analyses", sa.Column("id", sa.Integer, primary_key=True), sa.Column("feed_item_id", sa.Integer, sa.ForeignKey("feed_items.id", ondelete="CASCADE"), nullable=False), sa.Column("status", sa.String(20), nullable=False, server_default="requested"), sa.Column("requested_by_user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL")), sa.Column("claimed_at", sa.DateTime(timezone=True)), sa.Column("claimed_by", sa.String(255)), sa.Column("prompt_payload", postgresql.JSONB), sa.Column("result", postgresql.JSONB), sa.Column("recommendation", sa.String(30)), sa.Column("error", sa.Text), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("completed_at", sa.DateTime(timezone=True)))
    op.create_index("uq_feed_item_active_llm", "feed_item_llm_analyses", ["feed_item_id"], unique=True, postgresql_where=sa.text("status IN ('requested','claimed')"))
    op.create_table("document_llm_analyses", sa.Column("id", sa.Integer, primary_key=True), sa.Column("document_id", sa.Integer, sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False), sa.Column("status", sa.String(20), nullable=False, server_default="requested"), sa.Column("requested_by_user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL")), sa.Column("claimed_by", sa.String(255)), sa.Column("input_payload", postgresql.JSONB), sa.Column("result", postgresql.JSONB), sa.Column("next_status", sa.String(50)), sa.Column("error", sa.Text), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("completed_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    for table in ("document_llm_analyses", "feed_item_llm_analyses", "jobs", "feed_items", "feed_sources"):
        op.drop_table(table)
