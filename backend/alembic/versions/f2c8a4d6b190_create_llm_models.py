"""Add llm_models: the database-backed allowlist of language models (ADR-032), seeded with the current list."""
import sqlalchemy as sa
from alembic import op

revision = "f2c8a4d6b190"
down_revision = "e5a1c9d7b3f2"
branch_labels = None
depends_on = None

# (model_id, label, provider, external, verified, status, retires_on, note) — the allowlist that lived in code
# (library/llm_model_registry.py) when this table was introduced; kept inline so the migration never imports app code.
SEED = (
    ("Bielik-11B-v3.0-Instruct", "Bielik 11B v3.0 (CloudFerro)", "cloudferro", False, True, "active", None, None),
    ("Bielik-11B-v2.3-Instruct", "Bielik 11B v2.3 (CloudFerro)", "cloudferro", False, True, "active", None, None),
    ("gpt-4o-mini", "GPT-4o mini (OpenAI)", "openai", False, True, "active", None, None),
    ("gemini-3.1-flash-lite", "Gemini 3.1 Flash Lite (Google Vertex)", "google-vertexai", False, True, "active", None, None),
    ("gemini-3.5-flash-lite", "Gemini 3.5 Flash Lite (Google Vertex)", "google-vertexai", False, True, "active", None, None),
    ("openrouter/openai/gpt-4o-mini", "GPT-4o mini (OpenRouter)", "openrouter", True, False, "active", None, None),
    ("openrouter/google/gemini-2.5-flash-lite", "Gemini 2.5 Flash Lite (OpenRouter)", "openrouter", True, False,
     "deprecated", "2026-10-20",
     "Google wycofał ten model 2026-10-20; OpenRouter nadal go listuje. Ustaw status retired, gdy przestanie działać."),
    ("openrouter/mistralai/mistral-small-3.2-24b-instruct", "Mistral Small 3.2 24B (OpenRouter)", "openrouter", True,
     False, "active", None, None),
    ("openrouter/google/gemma-3-27b-it", "Gemma 3 27B (OpenRouter)", "openrouter", True, False, "active", None, None),
    ("openrouter/meta-llama/llama-3.1-8b-instruct", "Llama 3.1 8B (OpenRouter)", "openrouter", True, False, "active",
     None, None),
    ("openrouter/qwen/qwen-2.5-7b-instruct", "Qwen 2.5 7B (OpenRouter)", "openrouter", True, False, "active", None, None),
)


def upgrade():
    table = op.create_table(
        "llm_models",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("model_id", sa.String(100), nullable=False, unique=True),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("external", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("status", sa.String(12), nullable=False, server_default=sa.text("'active'")),
        sa.Column("retires_on", sa.Date(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('active', 'deprecated', 'retired')", name="ck_llm_models_status"),
    )
    import datetime

    op.bulk_insert(table, [
        {"model_id": model_id, "label": label, "provider": provider, "external": external, "verified": verified,
         "status": status, "retires_on": datetime.date.fromisoformat(retires_on) if retires_on else None, "note": note}
        for model_id, label, provider, external, verified, status, retires_on, note in SEED
    ])


def downgrade():
    op.drop_table("llm_models")
