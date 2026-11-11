"""world event kinds: ordering column and the kind 'terror_attack'

Revision ID: e5b8d2f6a173
Revises: d4a7c1e9b835
Create Date: 2026-11-11 00:00:00.000000

``geo_event_kinds`` becomes the only place the kinds are kept (code only reads it, see
``library/geo_event_kind_store.py``): it gets a ``sort_order`` column so the picker order no longer depends on a
list in code, and the kind ``terror_attack`` ("Atak terrorystyczny") is added.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5b8d2f6a173"
down_revision: Union[str, None] = "d4a7c1e9b835"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ORDER = {
    "election": 10, "summit": 20, "diplomatic": 30, "agreement": 40, "sanctions": 50, "conflict": 60,
    "terror_attack": 65, "exercise": 70, "protest": 80, "disaster": 90, "health": 100, "outage": 110,
    "cyber": 120, "product_launch": 130, "corporate": 140, "market": 150, "other": 9999,
}


def upgrade() -> None:
    op.add_column("geo_event_kinds", sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"))
    op.execute(
        sa.text("INSERT INTO geo_event_kinds (code, label) VALUES ('terror_attack', 'Atak terrorystyczny') "
                "ON CONFLICT (code) DO NOTHING")
    )
    for code, order in _ORDER.items():
        op.execute(sa.text("UPDATE geo_event_kinds SET sort_order = :o WHERE code = :c").bindparams(o=order, c=code))


def downgrade() -> None:
    op.execute("UPDATE geo_events SET kind = 'other' WHERE kind = 'terror_attack'")
    op.execute("DELETE FROM geo_event_kinds WHERE code = 'terror_attack'")
    op.drop_column("geo_event_kinds", "sort_order")
