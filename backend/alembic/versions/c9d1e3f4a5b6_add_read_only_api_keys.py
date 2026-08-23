"""add globally enforced read-only API keys

Revision ID: c9d1e3f4a5b6
Revises: b7a9d8c6e5f4, e8b71d92c5af
Create Date: 2026-08-23
"""
from typing import Sequence, Union

from alembic import op


revision: str = "c9d1e3f4a5b6"
down_revision: Union[str, Sequence[str], None] = ("b7a9d8c6e5f4", "e8b71d92c5af")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Earlier installations receive PostgreSQL's implicit
    # ``api_keys_kind_check`` name; the init SQL has no stable name. Replace
    # either form with one named constraint.
    op.execute("ALTER TABLE api_keys DROP CONSTRAINT IF EXISTS api_keys_kind_check")
    op.execute("ALTER TABLE api_keys DROP CONSTRAINT IF EXISTS ck_api_keys_kind")
    op.execute(
        "ALTER TABLE api_keys ADD CONSTRAINT ck_api_keys_kind "
        "CHECK (kind IN ('user', 'service', 'read_only'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE api_keys DROP CONSTRAINT IF EXISTS ck_api_keys_kind")
    op.execute(
        "ALTER TABLE api_keys ADD CONSTRAINT ck_api_keys_kind "
        "CHECK (kind IN ('user', 'service'))"
    )
