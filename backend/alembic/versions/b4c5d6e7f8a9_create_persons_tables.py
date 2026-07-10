"""create persons, person_aliases, document_persons

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-07-10 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b4c5d6e7f8a9"
down_revision: Union[str, None] = "a3b4c5d6e7f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # IF NOT EXISTS: the same objects may already have been created by the
    # Docker init script 23-create-persons-tables.sql on a fresh database.
    # pg_trgm is installed by 02-create-extension.sql; CREATE EXTENSION here
    # keeps the migration self-contained for pre-existing databases.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS persons (
            id             SERIAL PRIMARY KEY,
            uuid           VARCHAR(100) NOT NULL DEFAULT gen_random_uuid() UNIQUE,
            canonical_name TEXT NOT NULL,
            wikidata_qid   VARCHAR(20) UNIQUE,
            description    TEXT,
            created_at     TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_persons_canonical_name_trgm "
        "ON persons USING gin (canonical_name gin_trgm_ops)"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS person_aliases (
            id        SERIAL PRIMARY KEY,
            person_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
            alias     TEXT NOT NULL,
            UNIQUE (person_id, alias)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_person_aliases_alias_trgm "
        "ON person_aliases USING gin (alias gin_trgm_ops)"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS document_persons (
            id          SERIAL PRIMARY KEY,
            document_id INTEGER NOT NULL REFERENCES web_documents(id) ON DELETE CASCADE,
            person_id   INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
            raw_mention TEXT NOT NULL,
            confidence  VARCHAR(20) NOT NULL,
            created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
            UNIQUE (document_id, person_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_document_persons_document_id ON document_persons(document_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_document_persons_person_id ON document_persons(person_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS document_persons")
    op.execute("DROP TABLE IF EXISTS person_aliases")
    op.execute("DROP TABLE IF EXISTS persons")
