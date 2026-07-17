"""create cited publications

Revision ID: c7d8e9f0a1b2
Revises: b6c7d8e9f0a1
Create Date: 2026-07-17 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "c7d8e9f0a1b2"
down_revision: Union[str, None] = "b6c7d8e9f0a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE cited_publications (
            id SERIAL PRIMARY KEY,
            title TEXT,
            journal TEXT,
            publication_year INTEGER,
            doi TEXT,
            pmid VARCHAR(20),
            pmcid VARCHAR(30),
            canonical_url TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE UNIQUE INDEX uq_cited_publications_doi ON cited_publications (LOWER(doi)) WHERE doi IS NOT NULL")
    op.execute("CREATE UNIQUE INDEX uq_cited_publications_pmid ON cited_publications (pmid) WHERE pmid IS NOT NULL")
    op.execute("CREATE UNIQUE INDEX uq_cited_publications_pmcid ON cited_publications (UPPER(pmcid)) WHERE pmcid IS NOT NULL")
    op.execute("CREATE UNIQUE INDEX uq_cited_publications_url ON cited_publications (canonical_url)")
    op.execute("""
        CREATE TABLE document_cited_publications (
            id SERIAL PRIMARY KEY,
            document_id INTEGER NOT NULL REFERENCES web_documents(id) ON DELETE CASCADE,
            publication_id INTEGER NOT NULL REFERENCES cited_publications(id) ON DELETE CASCADE,
            chunk_id INTEGER REFERENCES document_chunks(id) ON DELETE SET NULL,
            raw_citation TEXT NOT NULL,
            evidence_excerpt TEXT,
            extraction_method VARCHAR(30) NOT NULL,
            review_status VARCHAR(30) NOT NULL DEFAULT 'auto_accepted',
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            UNIQUE (document_id, publication_id)
        )
    """)
    op.execute("CREATE INDEX idx_document_cited_publications_document ON document_cited_publications(document_id)")
    op.execute("CREATE INDEX idx_document_cited_publications_publication ON document_cited_publications(publication_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS document_cited_publications")
    op.execute("DROP TABLE IF EXISTS cited_publications")
