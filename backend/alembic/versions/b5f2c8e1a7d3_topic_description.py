"""Short description of a topic, sent to the topic-suggestion model next to the name."""

import sqlalchemy as sa
from alembic import op

revision = "b5f2c8e1a7d3"
down_revision = "e8c3a1f5b794"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("content_groups", sa.Column("description", sa.String(300)))


def downgrade() -> None:
    op.drop_column("content_groups", "description")
