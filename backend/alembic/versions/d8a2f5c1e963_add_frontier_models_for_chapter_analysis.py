"""Add two frontier models (via OpenRouter) to the llm_models allowlist.

The chapter analyses (tone, period, dated events) ran on a cheap local-class model. A text often only NAMES a
historical event ("Monachium 38", "kongres westfalski") and the year has to come from the model's own knowledge, which
a small model does not have. Both ids were checked against the public OpenRouter catalog on 2026-11-19; prices and
context windows are read from that catalog at runtime, never stored here. ``verified`` stays false until a human has
run them. The rows are a normal allowlist entry: either can be retired later with ``PATCH /llm_models/<id>``.

Revision ID: d8a2f5c1e963
Revises: b3f7d1a9c248
"""

from alembic import op
import sqlalchemy as sa

revision = "d8a2f5c1e963"
down_revision = "b3f7d1a9c248"
branch_labels = None
depends_on = None

# (model_id, label) — all external, provider openrouter, not yet verified by a human.
ADDED = (
    ("openrouter/anthropic/claude-sonnet-5.5", "Claude Sonnet 5.5 (OpenRouter)"),
    ("openrouter/anthropic/claude-fable-5.2", "Claude Fable 5.2 (OpenRouter)"),
)


def upgrade():
    # A row someone already added by hand through POST /llm_models is left as it is.
    statement = sa.text(
        "INSERT INTO llm_models (model_id, label, provider, external, verified, status) "
        "VALUES (:model_id, :label, 'openrouter', true, false, 'active') ON CONFLICT (model_id) DO NOTHING"
    )
    for model_id, label in ADDED:
        op.execute(statement.bindparams(model_id=model_id, label=label))


def downgrade():
    models = sa.table("llm_models", sa.column("model_id", sa.String))
    op.execute(models.delete().where(models.c.model_id.in_([row[0] for row in ADDED])))
