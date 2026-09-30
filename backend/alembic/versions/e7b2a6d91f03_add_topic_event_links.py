"""Allow contact group events in topics.

Revision ID: e7b2a6d91f03
Revises: a36fe7f31e23
"""

from alembic import op

revision = "e7b2a6d91f03"
down_revision = "a36fe7f31e23"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("topic_items") as batch:
        batch.drop_constraint("ck_topic_items_entity_type", type_="check")
        batch.create_check_constraint(
            "ck_topic_items_entity_type",
            "entity_type IN ('document', 'contact', 'contact_group_event', 'chat_conversation', 'chat_message')",
        )


def downgrade() -> None:
    op.execute("DELETE FROM topic_items WHERE entity_type = 'contact_group_event'")
    with op.batch_alter_table("topic_items") as batch:
        batch.drop_constraint("ck_topic_items_entity_type", type_="check")
        batch.create_check_constraint(
            "ck_topic_items_entity_type",
            "entity_type IN ('document', 'contact', 'chat_conversation', 'chat_message')",
        )
