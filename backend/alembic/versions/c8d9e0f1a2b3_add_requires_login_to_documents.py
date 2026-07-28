"""add requires_login to documents"""

from typing import Sequence, Union

from alembic import op


revision: str = "c8d9e0f1a2b3"
down_revision: Union[str, None] = "b7c8d9e0f1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS requires_login BOOLEAN NOT NULL DEFAULT FALSE"
    )
    op.execute(
        "UPDATE documents SET requires_login = TRUE WHERE document_type = 'social_media_post'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS requires_login")
