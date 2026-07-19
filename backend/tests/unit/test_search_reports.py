"""Unit tests for imports/search_reports.py (stage 12 reporting queries).

The queries are compiled to SQL and checked structurally — no database.
Live execution is covered by running the CLI against the NAS DB.
"""

from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")

from imports.search_reports import (  # noqa: E402
    interpretation_daily_rows,
    interpretation_error_rows,
    interpretation_feedback_rows,
    llm_cost_rows,
    models_without_pricing,
    unknown_cost_rows,
)


def _captured_sql(fn, *args):
    session = MagicMock()
    session.execute.return_value.all.return_value = []
    fn(session, *args)
    stmt = session.execute.call_args[0][0]
    return str(stmt.compile(compile_kwargs={"literal_binds": True}))


class TestInterpretationQueries:
    def test_daily_rows_group_by_day_and_status(self):
        sql = _captured_sql(interpretation_daily_rows, 30)
        assert "search_interpretation_logs" in sql
        assert "GROUP BY" in sql
        assert "status" in sql
        assert "fallback_used" in sql

    def test_error_rows_skip_null_codes(self):
        sql = _captured_sql(interpretation_error_rows, 30)
        assert "error_code IS NOT NULL" in sql
        assert "ORDER BY count(*) DESC" in sql

    def test_feedback_rows_group_by_verdict(self):
        sql = _captured_sql(interpretation_feedback_rows, 30)
        assert "feedback_verdict" in sql
        assert "GROUP BY" in sql


class TestLlmCostQueries:
    def test_cost_rows_group_by_provider_model_operation_currency(self):
        sql = _captured_sql(llm_cost_rows, 30)
        assert "llm_usage_logs" in sql
        for column in ("provider", "model", "operation", "cost_currency"):
            assert column in sql
        assert "sum(llm_usage_logs.cost_amount)" in sql

    def test_unknown_cost_rows_filter_on_status(self):
        sql = _captured_sql(unknown_cost_rows, 30)
        assert "cost_status = 'unknown'" in sql

    def test_models_without_pricing_diffs_usage_against_pricing(self):
        session = MagicMock()
        session.execute.side_effect = [
            MagicMock(all=MagicMock(return_value=[("cloudferro", "Bielik-11B-v3.0-Instruct")])),
            MagicMock(all=MagicMock(return_value=[
                ("cloudferro", "Bielik-11B-v3.0-Instruct"),
                ("openai", "gpt-4o-mini"),
            ])),
        ]
        missing = models_without_pricing(session)
        assert missing == [("openai", "gpt-4o-mini")]
