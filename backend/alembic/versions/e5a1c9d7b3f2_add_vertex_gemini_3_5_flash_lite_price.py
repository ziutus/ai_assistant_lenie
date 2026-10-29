"""Seed the Vertex AI price of gemini-3.5-flash-lite so its calls get a cost."""

from alembic import op

revision = "e5a1c9d7b3f2"
down_revision = "d3b8f1a6c924"
branch_labels = None
depends_on = None

VERSION = "google-vertexai-gemini-3-5-flash-lite-2026-10-29"


def upgrade() -> None:
    op.execute(f"""
        INSERT INTO llm_pricing (pricing_version, provider, model, pricing_mode,
                                 input_price_per_million, output_price_per_million,
                                 currency, effective_from, notes)
        SELECT '{VERSION}', 'google-vertexai', 'gemini-3.5-flash-lite', 'per_token', 0.30, 2.50, 'USD',
               DATE '2026-10-29',
               'Cennik Vertex AI (endpoint global) sprawdzony 2026-10-29; wyjście obejmuje tokeny rozumowania. '
               'Endpointy regionalne kosztują o 10% więcej.'
        WHERE NOT EXISTS (
            SELECT 1 FROM llm_pricing existing
            WHERE existing.provider = 'google-vertexai' AND existing.model = 'gemini-3.5-flash-lite'
              AND existing.effective_to IS NULL
        )
    """)


def downgrade() -> None:
    op.execute(f"UPDATE llm_usage_logs SET pricing_version = NULL WHERE pricing_version = '{VERSION}'")
    op.execute(f"DELETE FROM llm_pricing WHERE pricing_version = '{VERSION}'")
