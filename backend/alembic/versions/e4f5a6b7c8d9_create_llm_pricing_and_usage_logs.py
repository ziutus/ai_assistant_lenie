"""create versioned llm pricing and provider-agnostic usage logs

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-07-18 18:10:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "e4f5a6b7c8d9"
down_revision: Union[str, None] = "d3e4f5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE llm_pricing (
            id SERIAL PRIMARY KEY,
            pricing_version VARCHAR(64) NOT NULL UNIQUE,
            provider VARCHAR(50) NOT NULL,
            model VARCHAR(100) NOT NULL,
            pricing_mode VARCHAR(20) NOT NULL,
            input_price_per_million NUMERIC(12, 6),
            output_price_per_million NUMERIC(12, 6),
            currency VARCHAR(3) NOT NULL,
            effective_from DATE NOT NULL,
            effective_to DATE,
            notes TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_llm_pricing_mode CHECK (
                pricing_mode IN ('per_token', 'per_request', 'credits',
                                 'subscription', 'free', 'unknown')
            )
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX uq_llm_pricing_active_model
        ON llm_pricing(provider, model)
        WHERE effective_to IS NULL
    """)
    op.execute("""
        INSERT INTO llm_pricing (pricing_version, provider, model, pricing_mode,
                                 input_price_per_million, output_price_per_million,
                                 currency, effective_from, notes)
        VALUES
            ('cloudferro-bielik-2026-07-18', 'cloudferro', 'Bielik-11B-v3.0-Instruct',
             'per_token', 0.56, 0.56, 'EUR', '2026-07-18', NULL),
            ('cloudferro-bge-2026-07-18', 'cloudferro', 'BAAI/bge-multilingual-gemma2',
             'per_token', 0.50, 0.50, 'PLN', '2026-07-18',
             'kwota netto, bez VAT; embedding rozlicza tylko tokeny wejsciowe')
    """)
    op.execute("""
        CREATE TABLE llm_usage_logs (
            id BIGSERIAL PRIMARY KEY,
            request_id VARCHAR(64),
            search_interpretation_log_id INTEGER
                REFERENCES search_interpretation_logs(id) ON DELETE SET NULL,
            operation VARCHAR(50) NOT NULL,
            provider VARCHAR(50) NOT NULL,
            model VARCHAR(100) NOT NULL,
            endpoint VARCHAR(200),
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            total_tokens INTEGER,
            credits_used NUMERIC(18, 6),
            pricing_mode VARCHAR(20) NOT NULL DEFAULT 'unknown',
            pricing_version VARCHAR(64) REFERENCES llm_pricing(pricing_version),
            input_price_per_million NUMERIC(12, 6),
            output_price_per_million NUMERIC(12, 6),
            cost_amount NUMERIC(18, 10),
            cost_currency VARCHAR(3),
            cost_status VARCHAR(20) NOT NULL DEFAULT 'unknown',
            success BOOLEAN NOT NULL DEFAULT TRUE,
            error_code VARCHAR(100),
            called_at TIMESTAMP NOT NULL DEFAULT NOW(),
            latency_ms INTEGER,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_llm_usage_logs_pricing_mode CHECK (
                pricing_mode IN ('per_token', 'per_request', 'credits',
                                 'subscription', 'free', 'unknown')
            ),
            CONSTRAINT ck_llm_usage_logs_cost_status CHECK (
                cost_status IN ('reported', 'estimated', 'allocated', 'unknown')
            ),
            CONSTRAINT ck_llm_usage_logs_tokens_nonneg CHECK (
                (prompt_tokens IS NULL OR prompt_tokens >= 0)
                AND (completion_tokens IS NULL OR completion_tokens >= 0)
                AND (total_tokens IS NULL OR total_tokens >= 0)
            )
        )
    """)
    op.execute("CREATE INDEX idx_llm_usage_logs_called ON llm_usage_logs(called_at)")
    op.execute("CREATE INDEX idx_llm_usage_logs_operation_called ON llm_usage_logs(operation, called_at)")
    op.execute("CREATE INDEX idx_llm_usage_logs_provider_model_called ON llm_usage_logs(provider, model, called_at)")
    op.execute("""
        CREATE INDEX idx_llm_usage_logs_interpretation
        ON llm_usage_logs(search_interpretation_log_id)
        WHERE search_interpretation_log_id IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS llm_usage_logs")
    op.execute("DROP TABLE IF EXISTS llm_pricing")
