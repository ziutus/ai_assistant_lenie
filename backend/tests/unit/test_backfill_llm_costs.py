"""Historical costing uses only local rows and mocked sessions."""

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from imports.backfill_llm_costs import plan_backfill, run_backfill
from library.db.models import LlmPricing, LlmUsageLog


def usage(**kwargs):
    values = dict(id=1, provider="cloudferro", model="bge", operation="embedding", success=True,
                  prompt_tokens=1000, completion_tokens=None, total_tokens=1000, cost_status="unknown",
                  cost_amount=None, called_at=datetime(2026, 7, 18))
    return LlmUsageLog(**(values | kwargs))


def price(**kwargs):
    values = dict(provider="cloudferro", model="bge", pricing_version="bge-v1", pricing_mode="per_token",
                  input_price_per_million=Decimal("0.5"), output_price_per_million=Decimal("0.5"),
                  currency="PLN", effective_from=date(2026, 7, 18), effective_to=None)
    return LlmPricing(**(values | kwargs))


def test_embedding_snapshot_summary_and_idempotency():
    row = usage()
    updates, summary, skipped = plan_backfill([row], [price()])
    assert updates == [dict(id=1, cost_amount=Decimal("0.0005"), cost_currency="PLN", cost_status="estimated",
                            pricing_mode="per_token", pricing_version="bge-v1",
                            input_price_per_million=Decimal("0.5"), output_price_per_million=Decimal("0.5"))]
    group = summary["cloudferro", "bge", "PLN"]
    assert (group.rows, group.prompt_tokens, group.completion_tokens, group.total_cost) == (1, 1000, 0, Decimal("0.0005"))
    assert not skipped
    assert row.cost_amount is None and row.completion_tokens is None
    for key, value in updates[0].items():
        setattr(row, key, value)
    assert plan_backfill([row], [price()]) == ([], {}, {})
    assert row.completion_tokens is None and row.total_tokens == 1000


def test_historical_exclusive_end_and_currency_groups():
    old = price(effective_to=date(2026, 8, 1))
    new = price(effective_from=date(2026, 8, 1), currency="EUR", pricing_version="bge-v2",
                input_price_per_million=Decimal("1"))
    rows = [usage(called_at=datetime(2026, 7, 31, 23, 59)),
            usage(id=2, called_at=datetime(2026, 8, 1)),
            usage(id=3, called_at=datetime(2026, 7, 17))]
    updates, summary, skipped = plan_backfill(rows, [new, old])
    assert [row["pricing_version"] for row in updates] == ["bge-v1", "bge-v2"]
    assert summary["cloudferro", "bge", "EUR"].total_cost == Decimal("0.001")
    assert summary["cloudferro", "bge", "PLN"].total_cost == Decimal("0.0005")
    assert skipped == {"no price": 1}


def test_protected_rows_missing_tokens_and_missing_prices():
    rows = [usage(cost_status="reported"), usage(cost_status="estimated"), usage(success=False),
            usage(cost_amount=Decimal(0)), usage(prompt_tokens=None),
            usage(operation="chat", completion_tokens=None), usage(model="missing")]
    updates, summary, skipped = plan_backfill(rows, [price()])
    assert updates == [] and summary == {}
    assert skipped == {"no tokens": 2, "no price": 1}


@pytest.mark.parametrize("kwargs", [dict(pricing_mode="subscription"), dict(input_price_per_million=None)])
def test_uncomputable_price_is_skipped(kwargs):
    assert plan_backfill([usage()], [price(**kwargs)])[2] == {"no price": 1}


def test_chat_counts_output_and_aggregates():
    updates, summary, _ = plan_backfill(
        [usage(operation="chat", completion_tokens=500), usage(id=2)], [price()],
    )
    assert updates[0]["cost_amount"] == Decimal("0.0007500000")
    group = summary["cloudferro", "bge", "PLN"]
    assert group.rows == 2 and group.prompt_tokens == 2000 and group.completion_tokens == 500
    assert group.total_cost == Decimal("0.00125")


@pytest.mark.parametrize("apply", [False, True])
def test_batched_runner_filters_reports_and_writes_only_on_apply(apply, capsys):
    session = MagicMock()
    session.scalar.return_value = 2
    session.scalars.side_effect = [[price()], [usage(id=1, model="missing")], [usage(id=2)], []]
    with patch("imports.backfill_llm_costs.get_session", return_value=session):
        run_backfill(apply=apply, batch_size=1, provider="cloudferro", model="bge")
    queries = [call.args[0] for call in session.scalars.call_args_list][1:]
    assert [query.compile().params["id_1"] for query in queries] == [0, 1, 2]
    for query in queries:
        assert query.compile().params["provider_1"] == "cloudferro"
        assert query.compile().params["model_1"] == "bge"
        assert "LIMIT" in str(query)
    assert session.execute.call_count == int(apply)
    if apply:
        statement = session.execute.call_args.args[0]
        sql = str(statement)
        assigned = sql.split(" SET ")[1].split(" WHERE ")[0]
        assert "tokens=" not in assigned
        assert "cost_status" in sql and "cost_amount IS NULL" in sql
        assert session.commit.call_count == 2
    else:
        session.commit.assert_not_called()
    session.close.assert_called_once()
    report = capsys.readouterr().out
    assert "DRY-RUN" in report if not apply else "APPLY" in report
    assert "3 rows skipped: 1 no price / 2 no tokens" in report
    assert "0.0005000000 PLN" in report


def test_runner_rolls_back_and_closes_on_error():
    session = MagicMock()
    session.scalar.side_effect = RuntimeError("read failed")
    with patch("imports.backfill_llm_costs.get_session", return_value=session), pytest.raises(RuntimeError):
        run_backfill(apply=True)
    session.rollback.assert_called_once()
    session.close.assert_called_once()
