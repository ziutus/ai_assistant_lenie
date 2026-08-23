"""Add explicit author mapping for YouTube channel feeds.

Revision ID: af09cbe12345
Revises: c9d1e3f4a5b6
Create Date: 2026-08-23
"""

from alembic import op


revision = "af09cbe12345"
down_revision = "c9d1e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE feed_sources ADD COLUMN IF NOT EXISTS author_name TEXT")
    # The existing monitored channel has a deliberate creator mapping.  Keep
    # the UPDATE conditional so an administrator's later, more precise value
    # is never replaced by a migration re-run.
    op.execute("""
        UPDATE feed_sources
        SET author_name = 'Na Wschód od Bliskiego Wschodu'
        WHERE type = 'youtube_channel'
          AND lower(name) = lower('Na Wschód od Bliskiego Wschodu')
          AND COALESCE(btrim(author_name), '') = ''
    """)
    # Backfill only videos which have neither a display byline nor an existing
    # author link.  That makes the mapping safe for earlier imports without
    # overwriting manual or independently resolved authors.
    op.execute("""
        WITH target_documents AS (
            SELECT DISTINCT document.id
            FROM feed_sources AS feed
            JOIN feed_items AS item ON item.feed_source_id = feed.id
            JOIN documents AS document ON document.id = item.document_id
            WHERE feed.type = 'youtube_channel'
              AND lower(feed.name) = lower('Na Wschód od Bliskiego Wschodu')
              AND feed.author_name = 'Na Wschód od Bliskiego Wschodu'
              AND document.document_type = 'youtube'
              AND COALESCE(btrim(document.byline), '') = ''
              AND NOT EXISTS (
                  SELECT 1 FROM document_persons AS link
                  WHERE link.document_id = document.id AND link.role = 'author'
              )
        ), existing_person AS (
            SELECT min(id) AS id
            FROM persons
            WHERE lower(canonical_name) = lower('Na Wschód od Bliskiego Wschodu')
        ), created_person AS (
            INSERT INTO persons (canonical_name)
            SELECT 'Na Wschód od Bliskiego Wschodu'
            WHERE EXISTS (SELECT 1 FROM target_documents)
              AND NOT EXISTS (SELECT 1 FROM existing_person WHERE id IS NOT NULL)
            RETURNING id
        ), author_person AS (
            SELECT id FROM existing_person WHERE id IS NOT NULL
            UNION ALL
            SELECT id FROM created_person
            LIMIT 1
        ), updated_documents AS (
            UPDATE documents AS document
            SET byline = 'Na Wschód od Bliskiego Wschodu', byline_method = 'manual'
            FROM target_documents AS target
            WHERE document.id = target.id
            RETURNING document.id
        )
        INSERT INTO document_persons (document_id, person_id, raw_mention, confidence, role)
        SELECT document.id, author.id, 'Na Wschód od Bliskiego Wschodu', 'manual_confirmed', 'author'
        FROM updated_documents AS document
        CROSS JOIN author_person AS author
        ON CONFLICT (document_id, person_id) DO UPDATE
        SET role = 'author', confidence = 'manual_confirmed'
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE feed_sources DROP COLUMN IF EXISTS author_name")
