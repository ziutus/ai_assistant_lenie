"""Allow document processing and legacy bridge jobs."""

from alembic import op

revision = "e0f1a2b3c4d5"
down_revision = "d9e0f1a2b3c4"
branch_labels = None
depends_on = None

_OLD = "type IN ('feed_check','feed_check_all','feed_auto_import','feed_daily','content_group_suggest')"
_NEW = "type IN ('feed_check','feed_check_all','feed_auto_import','feed_daily','content_group_suggest','document_prepare','legacy_aws_pull')"


def upgrade() -> None:
    op.drop_constraint("ck_jobs_type", "jobs", type_="check")
    op.create_check_constraint("ck_jobs_type", "jobs", _NEW)


def downgrade() -> None:
    op.drop_constraint("ck_jobs_type", "jobs", type_="check")
    op.create_check_constraint("ck_jobs_type", "jobs", _OLD)
