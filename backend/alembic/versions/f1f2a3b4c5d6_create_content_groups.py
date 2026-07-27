"""create shared content groups and suggestion tables"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f1f2a3b4c5d6"
down_revision: Union[str, tuple[str, str], None] = "f1e2d3c4b5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "content_groups",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("priority_rank", sa.Integer),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("kind IN ('topic', 'priority')", name="ck_content_groups_kind"),
        sa.CheckConstraint(
            "(kind = 'topic' AND priority_rank IS NULL) OR "
            "(kind = 'priority' AND priority_rank BETWEEN 1 AND 100)",
            name="ck_content_groups_priority_rank",
        ),
    )
    op.create_index(
        "uq_content_groups_active_lower_name",
        "content_groups",
        [sa.text("lower(name)")],
        unique=True,
        postgresql_where=sa.text("archived_at IS NULL"),
    )

    op.create_table(
        "feed_item_group_memberships",
        sa.Column("feed_item_id", sa.Integer, sa.ForeignKey("feed_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("group_id", sa.Integer, sa.ForeignKey("content_groups.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("source", sa.String(20), nullable=False, server_default="manual"),
        sa.PrimaryKeyConstraint("feed_item_id", "group_id"),
        sa.CheckConstraint("source IN ('manual', 'llm_suggestion')", name="ck_feed_item_group_memberships_source"),
    )
    op.create_index("idx_feed_item_group_memberships_group_id", "feed_item_group_memberships", ["group_id"])

    op.create_table(
        "document_group_memberships",
        sa.Column("document_id", sa.Integer, sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("group_id", sa.Integer, sa.ForeignKey("content_groups.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("source", sa.String(20), nullable=False, server_default="manual"),
        sa.PrimaryKeyConstraint("document_id", "group_id"),
        sa.CheckConstraint("source IN ('manual', 'feed_import', 'chrome_link', 'llm_suggestion')", name="ck_document_group_memberships_source"),
    )
    op.create_index("idx_document_group_memberships_group_id", "document_group_memberships", ["group_id"])

    op.create_table(
        "content_group_suggestion_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("feed_item_id", sa.Integer, sa.ForeignKey("feed_items.id", ondelete="CASCADE")),
        sa.Column("document_id", sa.Integer, sa.ForeignKey("documents.id", ondelete="CASCADE")),
        sa.Column("job_id", sa.String(32), sa.ForeignKey("jobs.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("prompt_version", sa.String(30), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("catalog_snapshot", postgresql.JSONB, nullable=False),
        sa.Column("raw_result", postgresql.JSONB),
        sa.Column("error", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("(feed_item_id IS NOT NULL) <> (document_id IS NOT NULL)", name="ck_content_group_suggestion_runs_one_target"),
        sa.CheckConstraint("status IN ('queued', 'running', 'completed', 'error')", name="ck_content_group_suggestion_runs_status"),
    )
    op.create_index("uq_active_feed_group_suggestion_run", "content_group_suggestion_runs", ["feed_item_id"], unique=True, postgresql_where=sa.text("feed_item_id IS NOT NULL AND status IN ('queued', 'running')"))
    op.create_index("uq_active_document_group_suggestion_run", "content_group_suggestion_runs", ["document_id"], unique=True, postgresql_where=sa.text("document_id IS NOT NULL AND status IN ('queued', 'running')"))

    op.create_table(
        "content_group_suggestions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("run_id", sa.Integer, sa.ForeignKey("content_group_suggestion_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("group_id", sa.Integer, sa.ForeignKey("content_groups.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False),
        sa.Column("reason", sa.String(300)),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("membership_created", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("decided_by_user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("run_id", "group_id"),
        sa.CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_content_group_suggestions_confidence"),
        sa.CheckConstraint("status IN ('pending', 'accepted', 'dismissed', 'reverted')", name="ck_content_group_suggestions_status"),
    )
    op.add_column("feed_item_group_memberships", sa.Column("source_suggestion_id", sa.Integer, nullable=True))
    op.add_column("document_group_memberships", sa.Column("source_suggestion_id", sa.Integer, nullable=True))
    op.create_foreign_key("fk_feed_item_group_memberships_suggestion", "feed_item_group_memberships", "content_group_suggestions", ["source_suggestion_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_document_group_memberships_suggestion", "document_group_memberships", "content_group_suggestions", ["source_suggestion_id"], ["id"], ondelete="SET NULL")
    op.create_check_constraint("ck_feed_item_group_memberships_suggestion_source", "feed_item_group_memberships", "(source = 'llm_suggestion' AND source_suggestion_id IS NOT NULL) OR (source <> 'llm_suggestion' AND source_suggestion_id IS NULL)")
    op.create_check_constraint("ck_document_group_memberships_suggestion_source", "document_group_memberships", "(source = 'llm_suggestion' AND source_suggestion_id IS NOT NULL) OR (source <> 'llm_suggestion' AND source_suggestion_id IS NULL)")

    op.drop_constraint("ck_jobs_type", "jobs", type_="check")
    op.create_check_constraint("ck_jobs_type", "jobs", "type IN ('feed_check','feed_check_all','feed_auto_import','feed_daily','content_group_suggest')")
    op.execute("INSERT INTO content_groups (name, kind, priority_rank) SELECT 'Może kiedyś', 'priority', 100 WHERE NOT EXISTS (SELECT 1 FROM content_groups WHERE lower(name) = lower('Może kiedyś') AND archived_at IS NULL)")


def downgrade() -> None:
    op.drop_constraint("ck_jobs_type", "jobs", type_="check")
    op.create_check_constraint("ck_jobs_type", "jobs", "type IN ('feed_check','feed_check_all','feed_auto_import','feed_daily')")
    op.drop_constraint("ck_document_group_memberships_suggestion_source", "document_group_memberships", type_="check")
    op.drop_constraint("ck_feed_item_group_memberships_suggestion_source", "feed_item_group_memberships", type_="check")
    op.drop_constraint("fk_document_group_memberships_suggestion", "document_group_memberships", type_="foreignkey")
    op.drop_constraint("fk_feed_item_group_memberships_suggestion", "feed_item_group_memberships", type_="foreignkey")
    op.drop_column("document_group_memberships", "source_suggestion_id")
    op.drop_column("feed_item_group_memberships", "source_suggestion_id")
    op.drop_table("content_group_suggestions")
    op.drop_index("uq_active_document_group_suggestion_run", table_name="content_group_suggestion_runs")
    op.drop_index("uq_active_feed_group_suggestion_run", table_name="content_group_suggestion_runs")
    op.drop_table("content_group_suggestion_runs")
    op.drop_index("idx_document_group_memberships_group_id", table_name="document_group_memberships")
    op.drop_table("document_group_memberships")
    op.drop_index("idx_feed_item_group_memberships_group_id", table_name="feed_item_group_memberships")
    op.drop_table("feed_item_group_memberships")
    op.drop_index("uq_content_groups_active_lower_name", table_name="content_groups")
    op.drop_table("content_groups")
