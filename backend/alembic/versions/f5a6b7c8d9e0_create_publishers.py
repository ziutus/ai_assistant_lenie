"""create publishers and backfill document publisher domains

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-07-18 22:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "f5a6b7c8d9e0"
down_revision: Union[str, None] = "e4f5a6b7c8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE publishers (
            id SERIAL PRIMARY KEY,
            canonical_name TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX idx_publishers_canonical_name_lower ON publishers (LOWER(canonical_name))")
    op.execute("CREATE INDEX idx_publishers_canonical_name_trgm ON publishers USING gin (canonical_name gin_trgm_ops)")
    op.execute("""
        CREATE TABLE publisher_domains (
            id SERIAL PRIMARY KEY,
            publisher_id INTEGER NOT NULL REFERENCES publishers(id) ON DELETE CASCADE,
            domain TEXT NOT NULL UNIQUE
        )
    """)
    op.execute("CREATE INDEX idx_publisher_domains_publisher_id ON publisher_domains(publisher_id)")
    op.execute("CREATE INDEX idx_publisher_domains_domain_lower ON publisher_domains(LOWER(domain))")
    op.execute("ALTER TABLE web_documents ADD COLUMN publisher_id INTEGER REFERENCES publishers(id) ON DELETE SET NULL")
    op.execute("CREATE INDEX idx_web_documents_publisher_id ON web_documents(publisher_id)")

    # One initial publisher per normalized URL hostname.  The hostname is a
    # safe bootstrap name, editable later; discovery source is never read.
    op.execute("""
        WITH document_domains AS (
            SELECT id AS document_id,
                   LOWER(REGEXP_REPLACE(
                       SUBSTRING(url FROM '^(?:[a-zA-Z][a-zA-Z0-9+.-]*://)?(?:[^@/]+@)?([^/:?#]+)'),
                       '^www\\.', ''
                   )) AS domain
            FROM web_documents
        ), distinct_domains AS (
            SELECT DISTINCT domain FROM document_domains
            WHERE domain IS NOT NULL AND domain <> ''
        ), inserted_publishers AS (
            INSERT INTO publishers(canonical_name)
            SELECT domain FROM distinct_domains ORDER BY domain
            RETURNING id, canonical_name
        )
        INSERT INTO publisher_domains(publisher_id, domain)
        SELECT id, canonical_name FROM inserted_publishers
    """)
    op.execute("""
        WITH document_domains AS (
            SELECT id AS document_id,
                   LOWER(REGEXP_REPLACE(
                       SUBSTRING(url FROM '^(?:[a-zA-Z][a-zA-Z0-9+.-]*://)?(?:[^@/]+@)?([^/:?#]+)'),
                       '^www\\.', ''
                   )) AS domain
            FROM web_documents
        )
        UPDATE web_documents d SET publisher_id = pd.publisher_id
        FROM document_domains dd
        JOIN publisher_domains pd ON pd.domain = dd.domain
        WHERE d.id = dd.document_id
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE web_documents DROP COLUMN IF EXISTS publisher_id")
    op.execute("DROP TABLE IF EXISTS publisher_domains")
    op.execute("DROP TABLE IF EXISTS publishers")
