"""Seed the Vertex AI prices of the Gemini Flash-Lite models so their calls get a cost."""

from alembic import op

revision = "e5a1c9d7b3f2"
down_revision = "d3b8f1a6c924"
branch_labels = None
depends_on = None

VERSIONS = (
    "google-vertexai-gemini-3-1-flash-lite-2026-10-29",
    "google-vertexai-gemini-3-5-flash-lite-2026-10-29",
)
NOTE = ("Cennik Vertex AI (endpoint global) sprawdzony 2026-10-29; wyjście obejmuje tokeny rozumowania. "
        "Endpointy regionalne kosztują o 10% więcej.")


def upgrade() -> None:
    op.execute(f"""
        INSERT INTO llm_pricing (pricing_version, provider, model, pricing_mode,
                                 input_price_per_million, output_price_per_million,
                                 currency, effective_from, notes)
        SELECT version, 'google-vertexai', model, 'per_token', input_price, output_price, 'USD',
               DATE '2026-10-29', '{NOTE}'
        FROM (VALUES
            ('{VERSIONS[0]}', 'gemini-3.1-flash-lite', 0.25, 1.50),
            ('{VERSIONS[1]}', 'gemini-3.5-flash-lite', 0.30, 2.50)
        ) AS seeds(version, model, input_price, output_price)
        WHERE NOT EXISTS (
            SELECT 1 FROM llm_pricing existing
            WHERE existing.provider = 'google-vertexai' AND existing.model = seeds.model
              AND existing.effective_to IS NULL
        )
    """)


def downgrade() -> None:
    versions = ", ".join(f"'{version}'" for version in VERSIONS)
    op.execute(f"UPDATE llm_usage_logs SET pricing_version = NULL WHERE pricing_version IN ({versions})")
    op.execute(f"DELETE FROM llm_pricing WHERE pricing_version IN ({versions})")
