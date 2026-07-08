"""create api_keys table (service accounts + per-user keys)

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-07-07 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, None] = "d0e1f2a3b4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # IF NOT EXISTS: the same table may already have been created by the Docker
    # init script 20-create-api-keys.sql on a fresh database.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS api_keys (
            id           SERIAL PRIMARY KEY,
            kind         VARCHAR(10) NOT NULL CHECK (kind IN ('user', 'service')),
            user_id      INTEGER REFERENCES users(id) ON DELETE CASCADE,
            name         VARCHAR(100) NOT NULL UNIQUE,
            key_hash     CHAR(64) NOT NULL UNIQUE,
            key_prefix   VARCHAR(16) NOT NULL,
            active       BOOLEAN NOT NULL DEFAULT TRUE,
            created_at   TIMESTAMP NOT NULL DEFAULT NOW(),
            last_used_at TIMESTAMP,
            CONSTRAINT ck_api_keys_user_id_kind CHECK ((kind = 'user') = (user_id IS NOT NULL))
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_api_keys_user_id ON api_keys(user_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS api_keys")
