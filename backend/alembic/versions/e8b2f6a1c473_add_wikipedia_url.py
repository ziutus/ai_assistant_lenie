"""wikipedia_url on persons and organizations

Revision ID: e8b2f6a1c473
Revises: f4a9c2e7b681
Create Date: 2026-11-11 00:00:00.000000

A dedicated address of the Wikipedia article about a person / organization (next to ``persons.wikidata_qid``),
so the UI can show a Wikipedia chip beside the Wikidata one. For persons it is filled from the Wikidata sitelinks;
organizations have no Wikidata id yet, so theirs is entered by hand.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e8b2f6a1c473"
down_revision: Union[str, None] = "f4a9c2e7b681"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("persons", sa.Column("wikipedia_url", sa.Text()))
    op.add_column("organizations", sa.Column("wikipedia_url", sa.Text()))


def downgrade() -> None:
    op.drop_column("organizations", "wikipedia_url")
    op.drop_column("persons", "wikipedia_url")
