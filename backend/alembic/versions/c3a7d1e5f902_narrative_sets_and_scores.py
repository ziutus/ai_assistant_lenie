"""Narrative detection: narrative sets, narratives and per-document classifier scores."""

from alembic import op

revision = "c3a7d1e5f902"
down_revision = "b9d4f2a6c801"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS narrative_sets (
            id SERIAL PRIMARY KEY,
            slug VARCHAR(80) NOT NULL UNIQUE,
            name TEXT NOT NULL,
            actor VARCHAR(200) NOT NULL,
            kind VARCHAR(30) NOT NULL,
            source_url TEXT,
            source_note TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS narratives (
            id SERIAL PRIMARY KEY,
            set_id INTEGER NOT NULL REFERENCES narrative_sets (id) ON DELETE CASCADE,
            code VARCHAR(20) NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            UNIQUE (set_id, code)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS document_narrative_scores (
            id SERIAL PRIMARY KEY,
            document_id INTEGER NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
            narrative_id INTEGER NOT NULL REFERENCES narratives (id) ON DELETE CASCADE,
            model VARCHAR(60) NOT NULL,
            probability NUMERIC(4, 3) NOT NULL,
            confidence NUMERIC(4, 3),
            review VARCHAR(20),
            scored_at TIMESTAMP NOT NULL DEFAULT now(),
            UNIQUE (document_id, narrative_id, model)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_document_narrative_scores_narrative "
        "ON document_narrative_scores (narrative_id, probability)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS document_narrative_scores")
    op.execute("DROP TABLE IF EXISTS narratives")
    op.execute("DROP TABLE IF EXISTS narrative_sets")
