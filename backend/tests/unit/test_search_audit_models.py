"""Metadata tests for the stage-2 audit models (search-rebuild plan).

The tables are created by raw-SQL Alembic migrations (d3e4f5a6b7c8,
e4f5a6b7c8d9); these tests pin the ORM mapping to the same shape so a drift
between models.py and the migrations is caught without a database.
"""

import sqlalchemy as sa

from library.db.models import LlmPricing, LlmUsageLog, SearchInterpretationLog


def check_constraint_names(table):
    return {c.name for c in table.constraints if isinstance(c, sa.CheckConstraint)}


def index_names(table):
    return {i.name for i in table.indexes}


class TestSearchInterpretationLog:
    def test_required_columns(self):
        table = SearchInterpretationLog.__table__
        assert table.name == "search_interpretation_logs"
        for column in ("raw_query", "status", "created_at", "expires_at"):
            assert not table.c[column].nullable

    def test_feedback_and_audit_columns_exist(self):
        columns = set(SearchInterpretationLog.__table__.c.keys())
        assert {
            "model", "parser_version", "prompt_version", "raw_response", "parsed_query",
            "error_code", "error_message", "fallback_used", "llm_latency_ms",
            "search_latency_ms", "result_count", "feedback_verdict", "feedback_comment",
            "corrected_query", "feedback_at",
        } <= columns

    def test_status_and_feedback_checks(self):
        names = check_constraint_names(SearchInterpretationLog.__table__)
        assert "ck_search_interpretation_logs_status" in names
        assert "ck_search_interpretation_logs_feedback" in names

    def test_retention_index_present(self):
        assert "idx_search_interpretation_logs_expires" in index_names(SearchInterpretationLog.__table__)


class TestLlmPricing:
    def test_pricing_version_unique(self):
        assert LlmPricing.__table__.c.pricing_version.unique

    def test_money_columns_are_numeric(self):
        table = LlmPricing.__table__
        for column in ("input_price_per_million", "output_price_per_million"):
            column_type = table.c[column].type
            assert isinstance(column_type, sa.Numeric)
            assert (column_type.precision, column_type.scale) == (12, 6)

    def test_single_active_row_per_model_index(self):
        index = next(i for i in LlmPricing.__table__.indexes if i.name == "uq_llm_pricing_active_model")
        assert index.unique


class TestLlmUsageLog:
    def test_cost_amount_precision_matches_migration(self):
        column_type = LlmUsageLog.__table__.c.cost_amount.type
        assert isinstance(column_type, sa.Numeric)
        assert (column_type.precision, column_type.scale) == (18, 10)

    def test_interpretation_fk_survives_log_deletion(self):
        fk = next(iter(LlmUsageLog.__table__.c.search_interpretation_log_id.foreign_keys))
        assert fk.column.table.name == "search_interpretation_logs"
        assert fk.ondelete == "SET NULL"

    def test_pricing_snapshot_columns_exist(self):
        columns = set(LlmUsageLog.__table__.c.keys())
        assert {
            "pricing_mode", "pricing_version", "input_price_per_million",
            "output_price_per_million", "cost_amount", "cost_currency", "cost_status",
            "prompt_tokens", "completion_tokens", "total_tokens", "credits_used",
            "operation", "provider", "model", "latency_ms", "success", "error_code",
        } <= columns

    def test_cost_status_and_tokens_checks(self):
        names = check_constraint_names(LlmUsageLog.__table__)
        assert "ck_llm_usage_logs_cost_status" in names
        assert "ck_llm_usage_logs_pricing_mode" in names
        assert "ck_llm_usage_logs_tokens_nonneg" in names

    def test_aggregation_indexes_present(self):
        names = index_names(LlmUsageLog.__table__)
        assert {
            "idx_llm_usage_logs_called",
            "idx_llm_usage_logs_operation_called",
            "idx_llm_usage_logs_provider_model_called",
            "idx_llm_usage_logs_interpretation",
        } <= names
