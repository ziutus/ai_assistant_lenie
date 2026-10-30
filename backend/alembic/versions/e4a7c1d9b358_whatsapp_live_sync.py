"""WhatsApp live sync: bridge chat selection, sync state, WhatsApp identity on chat messages.

Revision ID: e4a7c1d9b358
Revises: d3b8f1a6c924
"""

import sqlalchemy as sa
from alembic import op

revision = "e4a7c1d9b358"
down_revision = "d3b8f1a6c924"
branch_labels = None
depends_on = None

_JOBS_BEFORE = (
    "type IN ('feed_check','feed_check_all','feed_auto_import','feed_daily','content_group_suggest',"
    "'document_prepare','entity_enrichment','legacy_aws_pull','obsidian_reimport','tool_candidate_detect',"
    "'retention_sweep')"
)
_JOBS_AFTER = _JOBS_BEFORE[:-1] + ",'whatsapp_sync')"


def upgrade() -> None:
    op.add_column("chat_messages", sa.Column("source", sa.String(10), nullable=False, server_default="import"))
    for name, length in (("wa_chat_jid", 128), ("wa_message_id", 128), ("wa_sender_jid", 128),
                         ("wa_sender_alt_jid", 128), ("media_status", 12), ("media_error", 200)):
        op.add_column("chat_messages", sa.Column(name, sa.String(length), nullable=True))
    op.add_column("chat_messages", sa.Column("is_from_me", sa.Boolean(), nullable=True))
    op.add_column("chat_messages", sa.Column("edited_at", sa.DateTime(), nullable=True))
    op.add_column("chat_messages", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    op.add_column("chat_messages", sa.Column("media_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("chat_messages", sa.Column("media_next_attempt_at", sa.DateTime(), nullable=True))
    op.create_index("uq_chat_messages_wa_identity", "chat_messages", ["wa_chat_jid", "wa_message_id"], unique=True)
    op.create_index("idx_chat_messages_media_pending", "chat_messages", ["media_status", "media_next_attempt_at"])

    op.create_table(
        "whatsapp_sync_chats",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("jid", sa.String(128), nullable=False, unique=True),
        sa.Column("display_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("is_group", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("chat_conversations.id", ondelete="SET NULL")),
        sa.Column("cursor_seq", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("buffered_events", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_message_at", sa.DateTime()),
        sa.Column("last_synced_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_whatsapp_sync_chats_enabled", "whatsapp_sync_chats", ["enabled"])
    op.create_table(
        "whatsapp_sync_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("connection_state", sa.String(20), nullable=False, server_default="unknown"),
        sa.Column("needs_pairing", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("bridge_reachable", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("account_jid", sa.String(128)),
        sa.Column("bridge_epoch", sa.String(64)),
        sa.Column("bridge_checked_at", sa.DateTime()),
        sa.Column("last_success_at", sa.DateTime()),
        sa.Column("last_error", sa.String(500)),
        sa.Column("last_error_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.drop_constraint("ck_jobs_type", "jobs", type_="check")
    op.create_check_constraint("ck_jobs_type", "jobs", _JOBS_AFTER)
    # Every 5 minutes; the job does nothing until WHATSAPP_BRIDGE_URL is configured.
    times = [f"{h:02d}:{m:02d}" for h in range(24) for m in range(0, 60, 5)]
    op.execute(
        sa.text(
            "INSERT INTO scheduled_tasks (id, enabled, timezone, times) "
            "VALUES ('whatsapp_sync', TRUE, 'Europe/Warsaw', CAST(:times AS jsonb))"
        ).bindparams(times=__import__("json").dumps(times))
    )


def downgrade() -> None:
    op.execute("DELETE FROM scheduled_tasks WHERE id = 'whatsapp_sync'")
    op.execute("DELETE FROM jobs WHERE type = 'whatsapp_sync'")
    op.drop_constraint("ck_jobs_type", "jobs", type_="check")
    op.create_check_constraint("ck_jobs_type", "jobs", _JOBS_BEFORE)
    op.drop_table("whatsapp_sync_state")
    op.drop_index("idx_whatsapp_sync_chats_enabled", table_name="whatsapp_sync_chats")
    op.drop_table("whatsapp_sync_chats")
    op.drop_index("idx_chat_messages_media_pending", table_name="chat_messages")
    op.drop_index("uq_chat_messages_wa_identity", table_name="chat_messages")
    for name in ("media_next_attempt_at", "media_attempts", "deleted_at", "edited_at", "is_from_me", "media_error",
                 "media_status", "wa_sender_alt_jid", "wa_sender_jid", "wa_message_id", "wa_chat_jid", "source"):
        op.drop_column("chat_messages", name)
