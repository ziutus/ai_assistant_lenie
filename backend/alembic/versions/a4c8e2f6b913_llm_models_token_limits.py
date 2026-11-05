"""Add context_length / max_output_tokens to llm_models so direct providers show their window like OpenRouter does."""
import sqlalchemy as sa
from alembic import op

revision = "a4c8e2f6b913"
down_revision = "f3a8c1d5e702"
branch_labels = None
depends_on = None

# (model_id, context_length, max_output_tokens) — from the providers' own documentation (checked 2026-11-05):
# Bielik 11B v2 technical report and v3 paper (32,768 context; no output limit published), OpenAI gpt-4o-mini
# (128,000 / 16,384), Google AI docs for Gemini 3.1 / 3.5 Flash-Lite (1,048,576 / 65,536).
LIMITS = (
    ("Bielik-11B-v3.0-Instruct", 32768, None),
    ("Bielik-11B-v2.3-Instruct", 32768, None),
    ("gpt-4o-mini", 128000, 16384),
    ("gemini-3.1-flash-lite", 1048576, 65536),
    ("gemini-3.5-flash-lite", 1048576, 65536),
)


def upgrade():
    op.add_column("llm_models", sa.Column("context_length", sa.Integer(), nullable=True))
    op.add_column("llm_models", sa.Column("max_output_tokens", sa.Integer(), nullable=True))
    op.create_check_constraint("ck_llm_models_context_length", "llm_models",
                               "context_length IS NULL OR context_length > 0")
    op.create_check_constraint("ck_llm_models_max_output_tokens", "llm_models",
                               "max_output_tokens IS NULL OR max_output_tokens > 0")
    table = sa.table("llm_models", sa.column("model_id", sa.String), sa.column("context_length", sa.Integer),
                     sa.column("max_output_tokens", sa.Integer))
    for model_id, context_length, max_output in LIMITS:
        op.execute(table.update().where(table.c.model_id == model_id).values(
            context_length=context_length, max_output_tokens=max_output))


def downgrade():
    op.drop_constraint("ck_llm_models_max_output_tokens", "llm_models", type_="check")
    op.drop_constraint("ck_llm_models_context_length", "llm_models", type_="check")
    op.drop_column("llm_models", "max_output_tokens")
    op.drop_column("llm_models", "context_length")
