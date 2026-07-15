"""create information provenance tables

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-07-15 13:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "d2e3f4a5b6c7"
down_revision: Union[str, None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS information_sources (
            id SERIAL PRIMARY KEY,
            canonical_name TEXT NOT NULL UNIQUE,
            source_type VARCHAR(30),
            domain TEXT,
            description TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS information_source_aliases (
            id SERIAL PRIMARY KEY,
            source_id INTEGER NOT NULL REFERENCES information_sources(id) ON DELETE CASCADE,
            alias TEXT NOT NULL,
            UNIQUE (source_id, alias)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS document_information_sources (
            id SERIAL PRIMARY KEY,
            document_id INTEGER NOT NULL REFERENCES web_documents(id) ON DELETE CASCADE,
            source_id INTEGER NOT NULL REFERENCES information_sources(id) ON DELETE CASCADE,
            role VARCHAR(30) NOT NULL,
            raw_mention TEXT NOT NULL,
            source_url TEXT,
            evidence_excerpt TEXT,
            confidence INTEGER,
            extraction_method VARCHAR(30) NOT NULL,
            review_status VARCHAR(30) NOT NULL DEFAULT 'auto_accepted',
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            UNIQUE (document_id, source_id, role)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_info_source_alias_lower ON information_source_aliases (LOWER(alias))")
    op.execute("CREATE INDEX IF NOT EXISTS idx_doc_info_sources_document ON document_information_sources (document_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_doc_info_sources_source_role ON document_information_sources (source_id, role)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS document_information_sources")
    op.execute("DROP TABLE IF EXISTS information_source_aliases")
    op.execute("DROP TABLE IF EXISTS information_sources")
