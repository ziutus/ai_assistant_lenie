"""Keep only OpenRouter and CloudFerro models in the llm_models allowlist.

Spending is controlled through two providers for now (OpenRouter and CloudFerro). Direct OpenAI and Google Vertex
models stayed in the pickers although they fail without credits (OpenAI: 429 insufficient_quota) or with an expired
authorization (Vertex), and the picker's availability check only tests that credentials exist, not that they work.
They are hidden with status ``retired`` (the rows stay, so ``PATCH /llm_models/<id>`` with ``status: active`` brings one
back). ``openrouter/google/gemini-2.5-flash-lite`` was marked deprecated with a retirement date of 2026-10-20, which has
passed, so it is deleted like the models removed in b3f7d1a9c248.

Revision ID: f6b1a9c4d7e2
Revises: d8a2f5c1e963
"""

import datetime

from alembic import op
import sqlalchemy as sa

revision = "f6b1a9c4d7e2"
down_revision = "d8a2f5c1e963"
branch_labels = None
depends_on = None

# (model_id, label, retires_on, note) — enough to restore the deleted row on downgrade.
REMOVED = (
    (
        "openrouter/google/gemini-2.5-flash-lite", "Gemini 2.5 Flash Lite (OpenRouter)", datetime.date(2026, 10, 20),
        "Google wycofał ten model 2026-10-20; OpenRouter nadal go listuje. Ustaw status retired, gdy przestanie działać.",
    ),
)
# Hidden, not deleted: direct providers other than CloudFerro.
RETIRED = ("gpt-4o-mini", "gemini-3.1-flash-lite", "gemini-3.5-flash-lite")


def upgrade():
    models = sa.table("llm_models", sa.column("model_id", sa.String), sa.column("status", sa.String))
    op.execute(models.delete().where(models.c.model_id.in_([row[0] for row in REMOVED])))
    op.execute(models.update().where(models.c.model_id.in_(RETIRED)).values(status="retired"))


def downgrade():
    models = sa.table(
        "llm_models",
        sa.column("model_id", sa.String),
        sa.column("label", sa.String),
        sa.column("provider", sa.String),
        sa.column("external", sa.Boolean),
        sa.column("verified", sa.Boolean),
        sa.column("status", sa.String),
        sa.column("retires_on", sa.Date),
        sa.column("note", sa.Text),
    )
    op.execute(models.update().where(models.c.model_id.in_(RETIRED)).values(status="active"))
    op.bulk_insert(models, [
        {"model_id": model_id, "label": label, "provider": "openrouter", "external": True, "verified": False,
         "status": "deprecated", "retires_on": retires_on, "note": note}
        for model_id, label, retires_on, note in REMOVED
    ])
