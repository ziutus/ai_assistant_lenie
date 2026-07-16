"""add review status to document_removed_lines

Revision ID: b6c7d8e9f0a1
Revises: a5b6c7d8e9f0
Create Date: 2026-07-16 15:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "b6c7d8e9f0a1"
down_revision: Union[str, None] = "a5b6c7d8e9f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE document_removed_lines "
        "ADD COLUMN IF NOT EXISTS review_status VARCHAR(20) NOT NULL DEFAULT 'pending'"
    )
    op.execute(
        "ALTER TABLE document_removed_lines "
        "ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMP"
    )
    op.execute(
        "ALTER TABLE document_removed_lines "
        "ADD COLUMN IF NOT EXISTS review_note TEXT"
    )
    op.execute(
        "ALTER TABLE document_removed_lines "
        "ADD COLUMN IF NOT EXISTS rule_reference VARCHAR(500)"
    )
    op.execute(
        "DO $$ BEGIN "
        "ALTER TABLE document_removed_lines ADD CONSTRAINT ck_removed_lines_review_status "
        "CHECK (review_status IN ('pending', 'rule_added', 'rejected', 'already_covered')); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_removed_lines_review_status "
        "ON document_removed_lines(review_status)"
    )

    # These removals produced the o2.pl rules introduced in PR #262.
    op.execute(
        "UPDATE document_removed_lines "
        "SET review_status = 'rule_added', reviewed_at = NOW(), "
        "review_note = 'Analyzed for o2.pl cleanup rules in PR #262', "
        "rule_reference = 'data/site_rules.json:o2.pl; article_cleaner.py:_clean_lines_wp' "
        "WHERE document_id = 357 AND run_id = 60 AND review_status = 'pending'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_removed_lines_review_status")
    op.execute(
        "ALTER TABLE document_removed_lines "
        "DROP CONSTRAINT IF EXISTS ck_removed_lines_review_status"
    )
    op.execute("ALTER TABLE document_removed_lines DROP COLUMN IF EXISTS rule_reference")
    op.execute("ALTER TABLE document_removed_lines DROP COLUMN IF EXISTS review_note")
    op.execute("ALTER TABLE document_removed_lines DROP COLUMN IF EXISTS reviewed_at")
    op.execute("ALTER TABLE document_removed_lines DROP COLUMN IF EXISTS review_status")
