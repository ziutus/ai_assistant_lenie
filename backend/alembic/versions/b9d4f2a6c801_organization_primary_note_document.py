"""Organizations: primary_note_document_id, a durable link to the Obsidian note document.

obsidian_note_path only names a vault file; once notes live in Lenie alone it is
meaningless, so the organization points at the imported obsidian_note document by id.
Existing links are backfilled from the path (documents.url = obsidian://<path>, with
or without the 02-wiedza/ prefix).
"""

from alembic import op

revision = "b9d4f2a6c801"
down_revision = "e2f6c0b4d8a5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE organizations ADD COLUMN IF NOT EXISTS primary_note_document_id INTEGER "
        "REFERENCES documents (id) ON DELETE SET NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_organizations_primary_note_document_id "
        "ON organizations (primary_note_document_id)"
    )
    op.execute(
        """
        UPDATE organizations o
        SET primary_note_document_id = (
            SELECT d.id FROM documents d
            WHERE d.document_type = 'obsidian_note'
              AND d.url IN ('obsidian://' || ltrim(o.obsidian_note_path, '/'),
                            'obsidian://02-wiedza/' || ltrim(o.obsidian_note_path, '/'))
            ORDER BY d.id LIMIT 1
        )
        WHERE o.obsidian_note_path IS NOT NULL AND o.primary_note_document_id IS NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_organizations_primary_note_document_id")
    op.execute("ALTER TABLE organizations DROP COLUMN IF EXISTS primary_note_document_id")
