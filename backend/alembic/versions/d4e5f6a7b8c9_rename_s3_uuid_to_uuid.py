"""rename s3_uuid to uuid in web_documents

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-04-07 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Rename column (preserves existing data)
    op.alter_column("web_documents", "s3_uuid", new_column_name="uuid")

    # 2. Backfill NULLs with generated UUIDs
    op.execute("UPDATE web_documents SET uuid = gen_random_uuid() WHERE uuid IS NULL")

    # 3. Add NOT NULL constraint and DEFAULT (safe after backfill)
    op.alter_column(
        "web_documents",
        "uuid",
        existing_type=sa.String(100),
        nullable=False,
        server_default=sa.text("gen_random_uuid()"),
    )

    # 4. Add UNIQUE constraint
    op.create_unique_constraint("uq_web_documents_uuid", "web_documents", ["uuid"])


def downgrade() -> None:
    # Reverse in opposite order
    op.drop_constraint("uq_web_documents_uuid", "web_documents", type_="unique")

    op.alter_column(
        "web_documents",
        "uuid",
        existing_type=sa.String(100),
        nullable=True,
        server_default=None,
    )

    op.alter_column("web_documents", "uuid", new_column_name="s3_uuid")
