"""add tool_candidate_detect job type

Revision ID: 2b3c4d5e6f7a
Revises: 0b1c2d3e4f5a
Create Date: 2026-08-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '2b3c4d5e6f7a'
down_revision: Union[str, Sequence[str], None] = '0b1c2d3e4f5a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD = "type IN ('feed_check','feed_check_all','feed_auto_import','feed_daily','content_group_suggest','document_prepare','entity_enrichment','legacy_aws_pull','obsidian_reimport')"
_NEW = "type IN ('feed_check','feed_check_all','feed_auto_import','feed_daily','content_group_suggest','document_prepare','entity_enrichment','legacy_aws_pull','obsidian_reimport','tool_candidate_detect')"


def upgrade() -> None:
    op.drop_constraint("ck_jobs_type", "jobs", type_="check")
    op.create_check_constraint("ck_jobs_type", "jobs", _NEW)


def downgrade() -> None:
    op.drop_constraint("ck_jobs_type", "jobs", type_="check")
    op.create_check_constraint("ck_jobs_type", "jobs", _OLD)
