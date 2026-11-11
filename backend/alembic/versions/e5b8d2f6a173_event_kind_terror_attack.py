"""world event kind: terror attack

Revision ID: e5b8d2f6a173
Revises: d4a7c1e9b835
Create Date: 2026-11-11 00:00:00.000000

Adds the kind ``terror_attack`` ("Atak terrorystyczny") to the ``geo_event_kinds`` dictionary.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "e5b8d2f6a173"
down_revision: Union[str, None] = "d4a7c1e9b835"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_NEW_KIND = ("terror_attack", "Atak terrorystyczny")


def upgrade() -> None:
    op.execute(
        f"INSERT INTO geo_event_kinds (code, label) VALUES ('{_NEW_KIND[0]}', '{_NEW_KIND[1]}') "
        "ON CONFLICT (code) DO NOTHING"
    )


def downgrade() -> None:
    op.execute("UPDATE geo_events SET kind = 'other' WHERE kind = 'terror_attack'")
    op.execute("DELETE FROM geo_event_kinds WHERE code = 'terror_attack'")
