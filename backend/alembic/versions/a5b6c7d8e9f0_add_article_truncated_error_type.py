"""add ARTICLE_TRUNCATED to document_status_error_types

Revision ID: a5b6c7d8e9f0
Revises: f4a5b6c7d8e9
Create Date: 2026-07-16 10:30:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "a5b6c7d8e9f0"
down_revision: Union[str, None] = "f4a5b6c7d8e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "INSERT INTO public.document_status_error_types (name) "
        "VALUES ('ARTICLE_TRUNCATED') ON CONFLICT (name) DO NOTHING"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE public.web_documents SET document_state_error = 'NONE' "
        "WHERE document_state_error = 'ARTICLE_TRUNCATED'"
    )
    op.execute("DELETE FROM public.document_status_error_types WHERE name = 'ARTICLE_TRUNCATED'")
