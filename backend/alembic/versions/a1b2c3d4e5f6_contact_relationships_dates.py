"""Add start_date/end_date to contact_relationships."""
from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "63f91b7e2a84"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE contact_relationships
            ADD COLUMN start_date DATE,
            ADD COLUMN end_date DATE,
            ADD CONSTRAINT ck_contact_relationships_dates CHECK (end_date >= start_date)
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE contact_relationships
            DROP CONSTRAINT ck_contact_relationships_dates,
            DROP COLUMN end_date,
            DROP COLUMN start_date
        """
    )
