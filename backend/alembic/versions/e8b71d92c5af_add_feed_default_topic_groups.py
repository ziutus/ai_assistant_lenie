"""Add default topic groups to feed sources.

Revision ID: e8b71d92c5af
Revises: ff6a7b8c9d0e
Create Date: 2026-08-23 00:00:00.000000
"""

from alembic import op


revision = "e8b71d92c5af"
down_revision = "ff6a7b8c9d0e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE feed_sources ADD COLUMN IF NOT EXISTS "
        "default_topic_group_ids JSONB NOT NULL DEFAULT '[]'::jsonb"
    )
    # Configure the existing YouTube feed requested by the product owner.
    # The condition keeps this migration safe in environments without either row.
    op.execute("""
        UPDATE feed_sources AS feed
        SET default_topic_group_ids = COALESCE(feed.default_topic_group_ids, '[]'::jsonb)
            || jsonb_build_array(topic.id)
        FROM content_groups AS topic
        WHERE lower(feed.name) = lower('Na Wschód od Bliskiego Wschodu')
          AND lower(topic.name) = lower('Geopolityka')
          AND topic.kind = 'topic'
          AND topic.archived_at IS NULL
          AND NOT COALESCE(feed.default_topic_group_ids, '[]'::jsonb) @> jsonb_build_array(topic.id)
    """)
    # Bring already imported transcripts from this feed in line with the new rule.
    op.execute("""
        INSERT INTO document_group_memberships (document_id, group_id, source)
        SELECT DISTINCT item.document_id, topic.id, 'feed_import'
        FROM feed_sources AS feed
        JOIN feed_items AS item ON item.feed_source_id = feed.id
        JOIN content_groups AS topic
          ON lower(topic.name) = lower('Geopolityka')
         AND topic.kind = 'topic'
         AND topic.archived_at IS NULL
        LEFT JOIN document_group_memberships AS membership
          ON membership.document_id = item.document_id AND membership.group_id = topic.id
        WHERE lower(feed.name) = lower('Na Wschód od Bliskiego Wschodu')
          AND item.document_id IS NOT NULL
          AND membership.document_id IS NULL
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE feed_sources DROP COLUMN IF EXISTS default_topic_group_ids")
