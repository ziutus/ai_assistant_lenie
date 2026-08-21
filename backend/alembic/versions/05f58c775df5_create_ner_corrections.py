"""create ner_corrections + ner_correction_applications

Revision ID: 05f58c775df5
Revises: 8aa9416453e6
Create Date: 2026-08-21 00:00:00.000000

Faza 6 of tmp/plan-ner-multiword-place-display-names.md: a human-curated,
lemma-keyed correction dictionary applied at entity-refresh time (mirrors
ner_exclusions, see c5d6e7f8a9b0_create_ner_exclusions.py), plus an
append-only audit log of every time a rule actually fired on a document.
Matching on the (spaCy-deterministic) lemma rather than a specific surface
form lets one human-approved correction generalize across every future
document that produces the same mangled lemma, instead of needing a new
approval per inflected form.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "05f58c775df5"
down_revision: Union[str, None] = "8aa9416453e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ner_corrections (
            id                     SERIAL PRIMARY KEY,
            match_lemma            TEXT NOT NULL,
            match_entity_type      VARCHAR(20) NOT NULL DEFAULT '*',
            corrected_text         TEXT NOT NULL,
            corrected_entity_type  VARCHAR(20),
            scope                  VARCHAR(10) NOT NULL DEFAULT 'global',
            author                 TEXT,
            reason                 TEXT NOT NULL,
            approved_by            TEXT NOT NULL,
            source_document_id     INTEGER REFERENCES documents(id) ON DELETE SET NULL,
            created_at             TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT ner_corrections_scope_check CHECK (scope IN ('global', 'author')),
            CONSTRAINT ner_corrections_author_required CHECK (scope != 'author' OR author IS NOT NULL)
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_ner_corrections_unique "
        "ON ner_corrections (LOWER(match_lemma), match_entity_type, scope, COALESCE(LOWER(author), ''))"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ner_correction_applications (
            id                  SERIAL PRIMARY KEY,
            document_id         INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            correction_id       INTEGER REFERENCES ner_corrections(id) ON DELETE SET NULL,
            entity_type_before  VARCHAR(20) NOT NULL,
            entity_text_before  TEXT NOT NULL,
            entity_type_after   VARCHAR(20) NOT NULL,
            entity_text_after   TEXT NOT NULL,
            applied_at          TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ner_correction_applications_document "
        "ON ner_correction_applications (document_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ner_correction_applications_correction "
        "ON ner_correction_applications (correction_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ner_correction_applications")
    op.execute("DROP TABLE IF EXISTS ner_corrections")
