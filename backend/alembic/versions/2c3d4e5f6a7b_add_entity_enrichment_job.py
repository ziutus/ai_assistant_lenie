"""add entity enrichment job type

Revision ID: 2c3d4e5f6a7b
Revises: 1b2c3d4e5f60
"""

from alembic import op

revision = "2c3d4e5f6a7b"
down_revision = "1b2c3d4e5f60"
branch_labels = None
depends_on = None

_OLD = "type IN ('feed_check','feed_check_all','feed_auto_import','feed_daily','content_group_suggest','document_prepare','legacy_aws_pull')"
_NEW = "type IN ('feed_check','feed_check_all','feed_auto_import','feed_daily','content_group_suggest','document_prepare','entity_enrichment','legacy_aws_pull')"


def upgrade() -> None:
    op.drop_constraint("ck_jobs_type", "jobs", type_="check")
    op.create_check_constraint("ck_jobs_type", "jobs", _NEW)


def downgrade() -> None:
    op.drop_constraint("ck_jobs_type", "jobs", type_="check")
    op.create_check_constraint("ck_jobs_type", "jobs", _OLD)
