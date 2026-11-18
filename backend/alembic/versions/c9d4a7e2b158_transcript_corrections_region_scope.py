"""Add the region scope to the STT phrase correction dictionary.

A ``region`` rule belongs to a country (``country_slug``, the ``kraj-<slug>`` tag of a document) and may
optionally be narrowed to one channel (``author``). The country tag narrows the context enough to allow a
single-word pattern, which global and channel rules still refuse.

Revision ID: c9d4a7e2b158
Revises: e8b2f6a1c473
"""

from alembic import op
import sqlalchemy as sa

revision = "c9d4a7e2b158"
down_revision = "e8b2f6a1c473"
branch_labels = None
depends_on = None

_INDEX = "uq_transcript_corrections_pattern_scope_author"


def upgrade():
    op.add_column("transcript_corrections", sa.Column("country_slug", sa.String(100)))
    op.drop_constraint("ck_transcript_corrections_scope", "transcript_corrections", type_="check")
    op.drop_constraint("ck_transcript_corrections_author", "transcript_corrections", type_="check")
    op.create_check_constraint(
        "ck_transcript_corrections_scope", "transcript_corrections",
        "scope IN ('global', 'author', 'region')",
    )
    op.create_check_constraint(
        "ck_transcript_corrections_author", "transcript_corrections",
        "(scope = 'global' AND author IS NULL AND country_slug IS NULL) OR "
        "(scope = 'author' AND author IS NOT NULL AND trim(author) <> '' AND country_slug IS NULL) OR "
        "(scope = 'region' AND country_slug IS NOT NULL AND trim(country_slug) <> '' "
        "AND (author IS NULL OR trim(author) <> ''))",
    )
    op.drop_index(_INDEX, table_name="transcript_corrections")
    op.create_index(
        _INDEX, "transcript_corrections",
        [sa.text("lower(pattern)"), "scope", sa.text("coalesce(author, '')"), sa.text("coalesce(country_slug, '')")],
        unique=True,
    )


def downgrade():
    op.execute("DELETE FROM transcript_corrections WHERE scope = 'region'")
    op.drop_index(_INDEX, table_name="transcript_corrections")
    op.create_index(
        _INDEX, "transcript_corrections",
        [sa.text("lower(pattern)"), "scope", sa.text("coalesce(author, '')")], unique=True,
    )
    op.drop_constraint("ck_transcript_corrections_author", "transcript_corrections", type_="check")
    op.drop_constraint("ck_transcript_corrections_scope", "transcript_corrections", type_="check")
    op.create_check_constraint(
        "ck_transcript_corrections_scope", "transcript_corrections", "scope IN ('global', 'author')",
    )
    op.create_check_constraint(
        "ck_transcript_corrections_author", "transcript_corrections",
        "(scope = 'global' AND author IS NULL) OR "
        "(scope = 'author' AND author IS NOT NULL AND trim(author) <> '')",
    )
    op.drop_column("transcript_corrections", "country_slug")
