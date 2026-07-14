"""create sources table

Revision ID: b0c1d2e3f4a5
Revises: a9b0c1d2e3f4
Create Date: 2026-07-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b0c1d2e3f4a5"
down_revision: Union[str, None] = "a9b0c1d2e3f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # IF NOT EXISTS: the same objects may already have been created by the
    # Docker init script 28-create-sources.sql on a fresh database.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS public.sources (
            id          SERIAL PRIMARY KEY,
            name        VARCHAR UNIQUE NOT NULL,
            description TEXT,
            url         TEXT,
            is_active   BOOLEAN NOT NULL DEFAULT TRUE
        )
        """
    )
    # Empty/whitespace-only source values would violate the FK after seeding.
    op.execute(
        "UPDATE web_documents SET source = NULL "
        "WHERE source IS NOT NULL AND btrim(source) = ''"
    )
    op.execute("INSERT INTO public.sources (name) VALUES ('own') ON CONFLICT (name) DO NOTHING")
    op.execute(
        """
        INSERT INTO public.sources (name)
        SELECT DISTINCT source FROM public.web_documents WHERE source IS NOT NULL
        ON CONFLICT (name) DO NOTHING
        """
    )
    # ON UPDATE CASCADE: renaming a source rewrites web_documents.source atomically.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_source') THEN
                ALTER TABLE public.web_documents
                    ADD CONSTRAINT fk_source FOREIGN KEY (source)
                    REFERENCES public.sources(name) ON UPDATE CASCADE;
            END IF;
        END $$
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE public.web_documents DROP CONSTRAINT IF EXISTS fk_source")
    op.execute("DROP TABLE IF EXISTS public.sources")
