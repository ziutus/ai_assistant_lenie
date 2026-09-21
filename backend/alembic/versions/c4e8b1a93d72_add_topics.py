"""Add polymorphic topics and topic items.

Revision ID: c4e8b1a93d72
Revises: a9c7e2d48f10
"""

from alembic import op
import sqlalchemy as sa

revision = "c4e8b1a93d72"
down_revision = "a9c7e2d48f10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "topics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("uq_topics_active_lower_name", "topics", [sa.text("lower(name)")], unique=True,
                    postgresql_where=sa.text("archived_at IS NULL"), sqlite_where=sa.text("archived_at IS NULL"))
    op.create_table(
        "topic_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("topic_id", sa.Integer(), sa.ForeignKey("topics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_type", sa.String(30), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("entity_type IN ('document', 'contact', 'chat_conversation', 'chat_message')",
                           name="ck_topic_items_entity_type"),
        sa.UniqueConstraint("topic_id", "entity_type", "entity_id", name="uq_topic_items_entity"),
    )
    op.create_index("idx_topic_items_entity", "topic_items", ["entity_type", "entity_id"])


def downgrade() -> None:
    op.drop_table("topic_items")
    op.drop_table("topics")
