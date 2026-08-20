"""store reviewed source relationships

Revision ID: 8e7d6c5b4a3f
Revises: 9d8e7f6a5b4c
"""
from alembic import op

revision = "8e7d6c5b4a3f"
down_revision = "9d8e7f6a5b4c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE document_source_relationships (
      id SERIAL PRIMARY KEY, document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
      chunk_id INTEGER REFERENCES document_chunks(id) ON DELETE SET NULL,
      subject_name TEXT NOT NULL, predicate VARCHAR(40) NOT NULL, object_name TEXT NOT NULL,
      evidence_excerpt TEXT NOT NULL, confidence INTEGER NOT NULL, status VARCHAR(20) NOT NULL DEFAULT 'proposed',
      created_at TIMESTAMP NOT NULL DEFAULT NOW(), decided_at TIMESTAMP,
      UNIQUE (document_id, subject_name, predicate, object_name, evidence_excerpt))""")
    op.execute("CREATE INDEX idx_document_source_relationships_doc_status ON document_source_relationships(document_id, status)")


def downgrade() -> None:
    op.execute("DROP TABLE document_source_relationships")
