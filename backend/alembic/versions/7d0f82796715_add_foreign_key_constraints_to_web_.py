"""add foreign key constraints to web_documents and websites_embeddings

Revision ID: 7d0f82796715
Revises: 906d2cc23d09
Create Date: 2026-03-11 06:12:48.022004

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '7d0f82796715'
down_revision: Union[str, Sequence[str], None] = '906d2cc23d09'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add FK constraints on document_state, document_state_error, document_type, and embedding model."""
    # Ensure no orphaned values exist before adding constraints.
    # Insert any missing values into lookup tables (ON CONFLICT DO NOTHING for idempotency).
    op.execute("""
        INSERT INTO document_status_types (name)
        SELECT DISTINCT document_state FROM web_documents
        WHERE document_state NOT IN (SELECT name FROM document_status_types)
        ON CONFLICT (name) DO NOTHING
    """)
    op.execute("""
        INSERT INTO document_status_error_types (name)
        SELECT DISTINCT document_state_error FROM web_documents
        WHERE document_state_error IS NOT NULL
          AND document_state_error NOT IN (SELECT name FROM document_status_error_types)
        ON CONFLICT (name) DO NOTHING
    """)
    op.execute("""
        INSERT INTO document_types (name)
        SELECT DISTINCT document_type FROM web_documents
        WHERE document_type NOT IN (SELECT name FROM document_types)
        ON CONFLICT (name) DO NOTHING
    """)
    op.execute("""
        INSERT INTO embedding_models (name)
        SELECT DISTINCT model FROM websites_embeddings
        WHERE model NOT IN (SELECT name FROM embedding_models)
        ON CONFLICT (name) DO NOTHING
    """)

    # web_documents: 3 FK constraints
    op.execute("""
        ALTER TABLE web_documents
            ADD CONSTRAINT fk_document_type
            FOREIGN KEY (document_type) REFERENCES document_types(name)
    """)
    op.execute("""
        ALTER TABLE web_documents
            ADD CONSTRAINT fk_document_state
            FOREIGN KEY (document_state) REFERENCES document_status_types(name)
    """)
    op.execute("""
        ALTER TABLE web_documents
            ADD CONSTRAINT fk_document_state_error
            FOREIGN KEY (document_state_error) REFERENCES document_status_error_types(name)
    """)

    # websites_embeddings: 1 FK constraint with cascade
    op.execute("""
        ALTER TABLE websites_embeddings
            ADD CONSTRAINT model_fk
            FOREIGN KEY (model) REFERENCES embedding_models(name) ON UPDATE CASCADE ON DELETE CASCADE
    """)


def downgrade() -> None:
    """Drop FK constraints in reverse order."""
    op.execute("ALTER TABLE websites_embeddings DROP CONSTRAINT IF EXISTS model_fk")
    op.execute("ALTER TABLE web_documents DROP CONSTRAINT IF EXISTS fk_document_state_error")
    op.execute("ALTER TABLE web_documents DROP CONSTRAINT IF EXISTS fk_document_state")
    op.execute("ALTER TABLE web_documents DROP CONSTRAINT IF EXISTS fk_document_type")
