"""WhatsApp group membership snapshots and thirty-minute sync schedule."""

import json

import sqlalchemy as sa
from alembic import op

revision = "b8e4f6a2c913"
down_revision = "a7d2c5e9f134"
branch_labels = None
depends_on = None

_JOBS_BEFORE = (
    "type IN ('feed_check','feed_check_all','feed_auto_import','feed_daily','content_group_suggest',"
    "'document_prepare','entity_enrichment','legacy_aws_pull','obsidian_reimport','tool_candidate_detect',"
    "'retention_sweep','whatsapp_sync')"
)
_JOBS_AFTER = _JOBS_BEFORE[:-1] + ",'whatsapp_groups_sync')"


def upgrade():
    op.create_table(
        "whatsapp_groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("jid", sa.String(128), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("is_community", sa.Boolean(), nullable=False),
        sa.Column("parent_jid", sa.String(128)),
        sa.Column("is_announce", sa.Boolean(), nullable=False),
        sa.Column("is_default_sub", sa.Boolean(), nullable=False),
        sa.Column("participant_count", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("chat_conversations.id", ondelete="SET NULL")),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("last_synced_at", sa.DateTime()),
        sa.Column("baseline_at", sa.DateTime()),
    )
    op.create_table(
        "whatsapp_group_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("whatsapp_groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("member_key", sa.String(128), nullable=False),
        sa.Column("jid", sa.String(128), nullable=False),
        sa.Column("lid", sa.String(128)),
        sa.Column("phone", sa.String(30)),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False),
        sa.Column("is_super_admin", sa.Boolean(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("left_at", sa.DateTime()),
        sa.Column("contact_id", sa.Integer(), sa.ForeignKey("contacts.id", ondelete="SET NULL")),
        sa.UniqueConstraint("group_id", "member_key", name="uq_whatsapp_group_member"),
    )
    op.create_table(
        "whatsapp_group_member_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("whatsapp_groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("member_key", sa.String(128), nullable=False),
        sa.Column("event_type", sa.String(5), nullable=False),
        sa.Column("phone", sa.String(30)),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("detected_at", sa.DateTime(), nullable=False),
        sa.Column("previous_synced_at", sa.DateTime()),
        sa.CheckConstraint("event_type IN ('join', 'leave')", name="ck_whatsapp_group_event_type"),
    )
    op.create_index("idx_whatsapp_group_events_detected", "whatsapp_group_member_events",
                    ["group_id", sa.text("detected_at DESC")])
    op.drop_constraint("ck_jobs_type", "jobs", type_="check")
    op.create_check_constraint("ck_jobs_type", "jobs", _JOBS_AFTER)
    times = [f"{hour:02d}:{minute:02d}" for hour in range(24) for minute in (0, 30)]
    op.execute(sa.text(
        "INSERT INTO scheduled_tasks (id, enabled, timezone, times) "
        "VALUES ('whatsapp_groups_sync', TRUE, 'Europe/Warsaw', CAST(:times AS jsonb))"
    ).bindparams(times=json.dumps(times)))


def downgrade():
    op.execute("DELETE FROM scheduled_tasks WHERE id = 'whatsapp_groups_sync'")
    op.execute("DELETE FROM jobs WHERE type = 'whatsapp_groups_sync'")
    op.drop_constraint("ck_jobs_type", "jobs", type_="check")
    op.create_check_constraint("ck_jobs_type", "jobs", _JOBS_BEFORE)
    op.drop_table("whatsapp_group_member_events")
    op.drop_table("whatsapp_group_members")
    op.drop_table("whatsapp_groups")
