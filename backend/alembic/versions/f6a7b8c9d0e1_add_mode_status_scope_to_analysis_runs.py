"""add mode, status and scope to document_analysis_runs

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-07-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # IF NOT EXISTS: the same columns may already have been added by the Docker
    # init script 15-add-analysis-run-workflow-columns.sql on a fresh database.
    op.execute(
        "ALTER TABLE document_analysis_runs "
        "ADD COLUMN IF NOT EXISTS mode VARCHAR(20) NOT NULL DEFAULT 'transcript'"
    )
    op.execute(
        "ALTER TABLE document_analysis_runs "
        "ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'created'"
    )
    op.execute(
        "ALTER TABLE document_analysis_runs "
        "ADD COLUMN IF NOT EXISTS scope VARCHAR(200)"
    )


def downgrade() -> None:
    op.drop_column("document_analysis_runs", "scope")
    op.drop_column("document_analysis_runs", "status")
    op.drop_column("document_analysis_runs", "mode")
