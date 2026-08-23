"""add needs_intervention job status

Revision ID: a1b2c3d4e5f6
Revises: fa12f5be1ae2
Create Date: 2026-08-23
"""

from typing import Sequence, Union

from alembic import op


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "fa12f5be1ae2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD = "status IN ('queued','running','done','failed','cancel_requested','cancelled')"
_NEW = "status IN ('queued','running','done','failed','needs_intervention','cancel_requested','cancelled')"


def upgrade() -> None:
    op.drop_constraint("ck_jobs_status", "jobs", type_="check")
    op.create_check_constraint("ck_jobs_status", "jobs", _NEW)


def downgrade() -> None:
    op.drop_constraint("ck_jobs_status", "jobs", type_="check")
    op.create_check_constraint("ck_jobs_status", "jobs", _OLD)
