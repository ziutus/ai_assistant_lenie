"""Add project_cards: structured hands-on project cards filterable by child age."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "b4c8e1a9d2f6"
down_revision = "7bc921e40a63"
branch_labels = None
depends_on = None

_EMPTY_ARRAY = sa.text("'[]'::jsonb")


def _list_column(name: str) -> sa.Column:
    return sa.Column(name, JSONB, nullable=False, server_default=_EMPTY_ARRAY)


def upgrade() -> None:
    op.create_table(
        "project_cards",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("series", sa.String(100), nullable=False),
        sa.Column("number", sa.Integer, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("topic", sa.Text),
        sa.Column("group_name", sa.String(100)),
        sa.Column("tagline", sa.Text),
        sa.Column("description", sa.Text),
        sa.Column("mechanism", sa.Text),
        sa.Column("how_it_works", sa.Text),
        sa.Column("age_min", sa.SmallInteger),
        sa.Column("age_max", sa.SmallInteger),
        sa.Column("time_min", sa.Integer),
        sa.Column("time_max", sa.Integer),
        sa.Column("difficulty", sa.SmallInteger),
        sa.Column("needs_adult", sa.Boolean, nullable=False, server_default=sa.text("false")),
        _list_column("materials"),
        _list_column("tools"),
        _list_column("steps"),
        _list_column("troubleshooting"),
        _list_column("variants"),
        sa.Column("safety", sa.Text),
        _list_column("what_child_does"),
        _list_column("what_adult_does"),
        _list_column("safety_checklist"),
        sa.Column("review_status", sa.String(20), nullable=False, server_default="imported"),
        sa.Column("review_notes", sa.Text),
        _list_column("import_flags"),
        sa.Column("source_file", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("series", "number", name="uq_project_cards_series_number"),
        sa.CheckConstraint("difficulty BETWEEN 1 AND 3", name="ck_project_cards_difficulty"),
        sa.CheckConstraint(
            "age_min IS NULL OR age_max IS NULL OR age_min <= age_max", name="ck_project_cards_age_range",
        ),
    )
    op.create_index("idx_project_cards_age", "project_cards", ["age_min", "age_max"])
    op.create_index("idx_project_cards_group", "project_cards", ["group_name"])


def downgrade() -> None:
    op.drop_index("idx_project_cards_group", table_name="project_cards")
    op.drop_index("idx_project_cards_age", table_name="project_cards")
    op.drop_table("project_cards")
