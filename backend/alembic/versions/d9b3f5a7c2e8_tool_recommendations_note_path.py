"""tool_recommendations: path of the Obsidian note that describes the tool

Revision ID: d9b3f5a7c2e8
Revises: c4e8a2d6f1b7
Create Date: 2026-10-23
"""

from alembic import op
import sqlalchemy as sa

revision = "d9b3f5a7c2e8"
down_revision = "c4e8a2d6f1b7"
branch_labels = None
depends_on = None

_NOTE_PREFIX = "Notatka: "


def upgrade() -> None:
    op.add_column("tool_recommendations", sa.Column("obsidian_note_path", sa.Text))
    # Radar entries imported from the vault kept the path in personal_note as "Notatka: <path>".
    op.execute(
        sa.text(
            "UPDATE tool_recommendations "
            "SET obsidian_note_path = btrim(substr(personal_note, length(:prefix) + 1)), "
            "    personal_note = NULL "
            "WHERE source_context = 'Vault Obsidian' AND personal_note LIKE :pattern "
            "  AND position(chr(10) in personal_note) = 0"
        ).bindparams(prefix=_NOTE_PREFIX, pattern=_NOTE_PREFIX + "%")
    )


def downgrade() -> None:
    op.drop_column("tool_recommendations", "obsidian_note_path")
