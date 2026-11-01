"""geopolitics: remember which prompt version produced an event or an assessment

Revision ID: b9d3f1a7c526
Revises: a4c8e2f6b013
Create Date: 2026-11-01 00:00:00.000000

The analysis prompt now lives in ``prompt_templates`` (task ``geopolitics_events``), where each edit is a new
version. Rows created by the LLM store the label of the version they came from (for example
``event_extraction-v3`` or ``event_extraction-builtin``), so a wording can be judged by what it produced.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b9d3f1a7c526"
down_revision: Union[str, None] = "a4c8e2f6b013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("geo_events", sa.Column("prompt_version", sa.String(length=40), nullable=True))
    op.add_column("country_relation_assessments", sa.Column("prompt_version", sa.String(length=40), nullable=True))


def downgrade() -> None:
    op.drop_column("country_relation_assessments", "prompt_version")
    op.drop_column("geo_events", "prompt_version")
