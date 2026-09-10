"""Move retention_sweep to 03:45 so it no longer shares 03:30 with obsidian_reimport."""

from alembic import op

revision = "c4a8d2b1f5e6"
down_revision = "b7e91a4c2d60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE scheduled_tasks SET times = '[\"03:45\"]'::jsonb WHERE id = 'retention_sweep'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE scheduled_tasks SET times = '[\"03:30\"]'::jsonb WHERE id = 'retention_sweep'"
    )
