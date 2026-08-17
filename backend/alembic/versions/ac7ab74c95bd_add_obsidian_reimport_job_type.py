"""add obsidian_reimport job type

Revision ID: ac7ab74c95bd
Revises: 41bdb9876895
Create Date: 2026-08-17 12:22:47.455376

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'ac7ab74c95bd'
down_revision: Union[str, Sequence[str], None] = '41bdb9876895'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD = "type IN ('feed_check','feed_check_all','feed_auto_import','feed_daily','content_group_suggest','document_prepare','entity_enrichment','legacy_aws_pull')"
_NEW = "type IN ('feed_check','feed_check_all','feed_auto_import','feed_daily','content_group_suggest','document_prepare','entity_enrichment','legacy_aws_pull','obsidian_reimport')"


def upgrade() -> None:
    op.drop_constraint("ck_jobs_type", "jobs", type_="check")
    op.create_check_constraint("ck_jobs_type", "jobs", _NEW)


def downgrade() -> None:
    op.drop_constraint("ck_jobs_type", "jobs", type_="check")
    op.create_check_constraint("ck_jobs_type", "jobs", _OLD)
