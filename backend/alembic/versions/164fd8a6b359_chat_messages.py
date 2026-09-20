"""Full chat message log import (chat_conversations, chat_messages) — WhatsApp full-history import, distinct from Contact.whatsapp_profile's LLM-distilled facts."""
from alembic import op
import sqlalchemy as sa

revision = "164fd8a6b359"
down_revision = "a6d31e8b902f"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "chat_conversations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("platform", sa.String(20), nullable=False, server_default=sa.text("'whatsapp'")),
        sa.Column("chat_key", sa.String(200), nullable=False, unique=True),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("last_imported_at", sa.DateTime(), nullable=True),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "conversation_id", sa.Integer(),
            sa.ForeignKey("chat_conversations.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("sender_name_raw", sa.String(255), nullable=False),
        sa.Column("contact_id", sa.Integer(), sa.ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=False),
        sa.Column("message_type", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("media_storage_key", sa.Text(), nullable=True),
        sa.Column("media_original_filename", sa.Text(), nullable=True),
        sa.Column("media_mime_type", sa.String(100), nullable=True),
        sa.Column("media_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("dedup_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "message_type IN ('text', 'image', 'video', 'audio', 'document', "
            "'contact_card', 'sticker', 'system', 'deleted')",
            name="ck_chat_messages_message_type",
        ),
    )
    op.create_index("idx_chat_messages_conversation_sent_at", "chat_messages", ["conversation_id", "sent_at"])
    op.create_index("idx_chat_messages_contact", "chat_messages", ["contact_id"])


def downgrade():
    op.drop_index("idx_chat_messages_contact", table_name="chat_messages")
    op.drop_index("idx_chat_messages_conversation_sent_at", table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_table("chat_conversations")
