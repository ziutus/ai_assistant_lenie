"""Remove two dead models from the llm_models allowlist.

Bielik 11B v2.3 is no longer served by CloudFerro (HTTP 404 "model does not exist") and Qwen 2.5 7B was retired on
OpenRouter ("no provider serves this model anymore"), so both only showed up in model pickers and failed when chosen.
Usage history (`llm_usage_logs`, `llm_pricing`) keeps the model names as plain text and is left untouched.

Revision ID: b3f7d1a9c248
Revises: e5c9a1d3b742
"""

from alembic import op
import sqlalchemy as sa

revision = "b3f7d1a9c248"
down_revision = "e5c9a1d3b742"
branch_labels = None
depends_on = None

# (model_id, label, provider, external, verified, context_length) — enough to restore the rows on downgrade.
REMOVED = (
    ("Bielik-11B-v2.3-Instruct", "Bielik 11B v2.3 (CloudFerro)", "cloudferro", False, True, 32768),
    ("openrouter/qwen/qwen-2.5-7b-instruct", "Qwen 2.5 7B (OpenRouter)", "openrouter", True, False, None),
)


def upgrade():
    models = sa.table("llm_models", sa.column("model_id", sa.String))
    op.execute(models.delete().where(models.c.model_id.in_([row[0] for row in REMOVED])))


def downgrade():
    models = sa.table(
        "llm_models",
        sa.column("model_id", sa.String),
        sa.column("label", sa.String),
        sa.column("provider", sa.String),
        sa.column("external", sa.Boolean),
        sa.column("verified", sa.Boolean),
        sa.column("status", sa.String),
        sa.column("context_length", sa.Integer),
    )
    op.bulk_insert(models, [
        {"model_id": model_id, "label": label, "provider": provider, "external": external, "verified": verified,
         "status": "active", "context_length": context_length}
        for model_id, label, provider, external, verified, context_length in REMOVED
    ])
