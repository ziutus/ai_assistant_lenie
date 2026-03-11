"""create lookup tables and seed data

Revision ID: 906d2cc23d09
Revises:
Create Date: 2026-03-10 15:37:15.309548

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '906d2cc23d09'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create 4 lookup tables and seed data."""
    # document_status_types (16 rows)
    op.execute("""
        CREATE TABLE IF NOT EXISTS public.document_status_types (
            id SERIAL PRIMARY KEY,
            name VARCHAR UNIQUE NOT NULL
        )
    """)
    op.execute("""
        INSERT INTO public.document_status_types (name) VALUES
            ('ERROR'), ('URL_ADDED'), ('NEED_TRANSCRIPTION'), ('TRANSCRIPTION_IN_PROGRESS'),
            ('TRANSCRIPTION_DONE'), ('TRANSCRIPTION_DONE_AND_SPLIT_BY_CHAPTERS'),
            ('NEED_MANUAL_REVIEW'), ('READY_FOR_TRANSLATION'), ('READY_FOR_EMBEDDING'),
            ('EMBEDDING_EXIST'), ('DOCUMENT_INTO_DATABASE'), ('NEED_CLEAN_TEXT'),
            ('NEED_CLEAN_MD'), ('TEXT_TO_MD_DONE'), ('MD_SIMPLIFIED'), ('TEMPORARY_ERROR')
        ON CONFLICT (name) DO NOTHING
    """)

    # document_status_error_types (17 rows)
    op.execute("""
        CREATE TABLE IF NOT EXISTS public.document_status_error_types (
            id SERIAL PRIMARY KEY,
            name VARCHAR UNIQUE NOT NULL
        )
    """)
    op.execute("""
        INSERT INTO public.document_status_error_types (name) VALUES
            ('NONE'), ('ERROR_DOWNLOAD'), ('LINK_SUMMARY_MISSING'), ('TITLE_MISSING'),
            ('TITLE_TRANSLATION_ERROR'), ('TEXT_MISSING'), ('TEXT_TRANSLATION_ERROR'),
            ('SUMMARY_TRANSLATION_ERROR'), ('NO_URL_ERROR'), ('EMBEDDING_ERROR'),
            ('MISSING_TRANSLATION'), ('TRANSLATION_ERROR'), ('REGEX_ERROR'),
            ('TEXT_TO_MD_ERROR'), ('NO_CAPTIONS_AVAILABLE'), ('CAPTIONS_LANGUAGE_MISMATCH'),
            ('CAPTIONS_FETCH_ERROR')
        ON CONFLICT (name) DO NOTHING
    """)

    # document_types (6 rows)
    op.execute("""
        CREATE TABLE IF NOT EXISTS public.document_types (
            id SERIAL PRIMARY KEY,
            name VARCHAR UNIQUE NOT NULL
        )
    """)
    op.execute("""
        INSERT INTO public.document_types (name) VALUES
            ('movie'), ('youtube'), ('link'), ('webpage'), ('text_message'), ('text')
        ON CONFLICT (name) DO NOTHING
    """)

    # embedding_models (7 rows)
    op.execute("""
        CREATE TABLE IF NOT EXISTS public.embedding_models (
            id SERIAL PRIMARY KEY,
            name VARCHAR UNIQUE NOT NULL
        )
    """)
    op.execute("""
        INSERT INTO public.embedding_models (name) VALUES
            ('text-embedding-ada-002'), ('amazon.titan-embed-text-v1'),
            ('amazon.titan-embed-text-v2:0'), ('dunzhang/stella_en_1.5B_v5'),
            ('BAAI/bge-m3'), ('BAAI/bge-multilingual-gemma2'),
            ('intfloat/e5-mistral-7b-instruct')
        ON CONFLICT (name) DO NOTHING
    """)


def downgrade() -> None:
    """Drop lookup tables in reverse dependency order."""
    op.execute("DROP TABLE IF EXISTS public.embedding_models")
    op.execute("DROP TABLE IF EXISTS public.document_types")
    op.execute("DROP TABLE IF EXISTS public.document_status_error_types")
    op.execute("DROP TABLE IF EXISTS public.document_status_types")
