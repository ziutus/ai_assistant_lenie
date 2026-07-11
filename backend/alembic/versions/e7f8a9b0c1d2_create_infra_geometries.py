"""create infra_geometries

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
Create Date: 2026-07-11 00:00:00.000000

Cache of Overpass API lookups for linear infrastructure (pipelines) by name —
same philosophy as geocode_cache: one live call ever per distinct query,
negative results cached too. geojson holds a simplified MultiLineString
rendered as polylines on the reader map (library/overpass_client.py).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "e7f8a9b0c1d2"
down_revision: Union[str, None] = "d6e7f8a9b0c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "infra_geometries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("query", sa.Text(), nullable=False, unique=True),
        sa.Column("resolved", sa.Boolean(), nullable=False),
        sa.Column("kind", sa.String(length=30)),
        sa.Column("substance", sa.String(length=30)),
        sa.Column("name", sa.Text()),
        sa.Column("wikidata_qid", sa.String(length=20)),
        sa.Column("geojson", JSONB()),
        sa.Column("provider", sa.String(length=20), nullable=False, server_default="overpass"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("infra_geometries")
