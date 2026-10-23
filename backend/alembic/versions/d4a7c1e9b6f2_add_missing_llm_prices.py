"""Seed missing prices so historical calls can be estimated."""

from alembic import op

revision = "d4a7c1e9b6f2"
down_revision = "c2e8a5d1f9b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO llm_pricing (pricing_version, provider, model, pricing_mode,
                                input_price_per_million, output_price_per_million,
                                currency, effective_from, notes)
        SELECT version, provider, model, 'per_token', input_price, output_price,
               currency, DATE '2026-07-18', notes
        FROM (VALUES
            ('openai-gpt-4o-mini-2026-07-18', 'openai', 'gpt-4o-mini', 0.15, 0.60, 'USD',
             'Cena z dokumentacji OpenAI sprawdzonej 2026-10-23; założono stałą cenę od pierwszego użycia.'),
            ('cloudferro-gemma-4-31b-2026-07-18', 'cloudferro', 'google/gemma-4-31B-it', 0.25, 0.50, 'EUR',
             'Cena podana przez właściciela z cennika CloudFerro 2026-10-23; '
             'założono stałą cenę od pierwszego użycia.'),
            ('cloudferro-mistral-small-4-2026-07-18', 'cloudferro',
             'mistralai/Mistral-Small-4-119B-2603', 0.15, 0.55, 'EUR',
             'Cena podana przez właściciela z cennika CloudFerro 2026-10-23; '
             'założono stałą cenę od pierwszego użycia.')
        ) AS seeds(version, provider, model, input_price, output_price, currency, notes)
        WHERE NOT EXISTS (
            SELECT 1 FROM llm_pricing existing
            WHERE existing.provider = seeds.provider AND existing.model = seeds.model
              AND existing.effective_to IS NULL
        )
    """)


def downgrade() -> None:
    versions = """('openai-gpt-4o-mini-2026-07-18',
                   'cloudferro-gemma-4-31b-2026-07-18',
                   'cloudferro-mistral-small-4-2026-07-18')"""
    op.execute(f"UPDATE llm_usage_logs SET pricing_version = NULL WHERE pricing_version IN {versions}")
    op.execute(f"DELETE FROM llm_pricing WHERE pricing_version IN {versions}")
