"""Create the curated STT phrase correction dictionary.

Revision ID: a71c9e2b406d
Revises: 8e2f7a6c901b
"""

from alembic import op
import sqlalchemy as sa

revision = "a71c9e2b406d"
down_revision = "8e2f7a6c901b"
branch_labels = None
depends_on = None


def upgrade():
    table = op.create_table(
        "transcript_corrections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pattern", sa.Text(), nullable=False),
        sa.Column("replacement", sa.Text(), nullable=False),
        sa.Column("scope", sa.String(10), nullable=False, server_default="global"),
        sa.Column("author", sa.Text()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("note", sa.Text()),
        sa.Column("created_by", sa.String(100)),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_hit_at", sa.DateTime()),
        sa.CheckConstraint("scope IN ('global', 'author')", name="ck_transcript_corrections_scope"),
        sa.CheckConstraint(
            "(scope = 'global' AND author IS NULL) OR "
            "(scope = 'author' AND author IS NOT NULL AND trim(author) <> '')",
            name="ck_transcript_corrections_author",
        ),
    )
    op.create_index(
        "uq_transcript_corrections_pattern_scope_author", "transcript_corrections",
        [sa.text("lower(pattern)"), "scope", sa.text("coalesce(author, '')")], unique=True,
    )
    op.bulk_insert(table, [{
        "pattern": "pi\u0119to Achillesa", "replacement": "pi\u0119ta Achillesa",
        "scope": "global", "note": "STT error in doc #10872: nominative phrase required",
        "created_by": "migration",
    }])


def downgrade():
    op.drop_table("transcript_corrections")
