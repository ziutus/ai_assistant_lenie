"""add variants to document_entities

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-07-11 00:00:00.000000

Surface forms of the entity as seen in the text ("Kijów", "Kijowa", "Kijowie").
The NER service returns them with every mention, but aggregation used to keep
only the lemma — the variants are what lets the chapter-scoped entity filter
(GET /document/<id>/chapter/<pos>/entities) find an entity in a chapter's text
regardless of Polish inflection. Empty array = row predates this column;
repopulated on the next entity refresh (POST /website_entities).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY

# revision identifiers, used by Alembic.
revision: str = "d6e7f8a9b0c1"
down_revision: Union[str, None] = "c5d6e7f8a9b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "document_entities",
        sa.Column(
            "variants",
            ARRAY(sa.Text),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("document_entities", "variants")
