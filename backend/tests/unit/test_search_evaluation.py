from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from library.llm_usage.pricing import CostEstimate, CostStatus
from library.search.evaluation import parsed_query_dict, score_case, summarize
from library.search.types import InterpretationStatus, ParsedSearchQuery, SearchSort


def _result(parsed, *, status=InterpretationStatus.PARSED):
    cost = CostEstimate(
        input_cost=Decimal("0.01"),
        output_cost=Decimal("0.01"),
        total_cost=Decimal("0.02"),
        currency="PLN",
        status=CostStatus.ESTIMATED,
    )
    usage = SimpleNamespace(usage_log_id=7, prompt_tokens=10, completion_tokens=5, total_tokens=15, cost=cost)
    return SimpleNamespace(parsed_query=parsed, status=status, fallback_used=False, interpretation_log_id=8, llm_latency_ms=100, usage=usage)


def test_parsed_query_dict_serializes_domain_values():
    data = parsed_query_dict(ParsedSearchQuery(query="x", published_on_from=date(2024, 1, 2), sort=SearchSort.PUBLISHED_DESC, interpretation_summary="ok"))
    assert data["published_on_from"] == "2024-01-02"
    assert data["sort"] == "published_desc"
    assert data["document_types"] == []


def test_score_case_checks_only_partial_expected_fields():
    case = {"id": "x", "category": "topic", "natural_query": "x", "expected": {"query": "x"}}
    scored = score_case(case, _result(ParsedSearchQuery(query="x", warnings=("extra",), interpretation_summary="ok")))
    assert scored["all_expected_fields_correct"] is True
    assert scored["valid_json"] is True
    assert scored["cost_amount"] == "0.02"


def test_score_case_classifies_validation_before_field_mismatch():
    case = {"id": "x", "category": "topic", "natural_query": "x", "expected": {"query": "wanted"}}
    scored = score_case(case, _result(ParsedSearchQuery(query="raw", interpretation_summary="fallback"), status=InterpretationStatus.VALIDATION_ERROR))
    assert scored["error_category"] == "validation_error"
    assert scored["valid_json"] is True


def test_summarize_aggregates_fields_usage_and_skipped_case():
    cases = [
        score_case({"id": "a", "category": "topic", "natural_query": "a", "expected": {"query": "a"}}, _result(ParsedSearchQuery(query="a", interpretation_summary="ok"))),
        score_case({"id": "b", "category": "topic", "natural_query": "b", "expected": {"query": "wrong"}}, _result(ParsedSearchQuery(query="b", interpretation_summary="ok"))),
    ]
    summary = summarize(cases, skipped_cases=1)
    assert summary["fixture_cases"] == 3
    assert summary["case_accuracy"] == 0.5
    assert summary["per_field"]["query"]["accuracy"] == 0.5
    assert summary["tokens_total"] == 30
    assert summary["cost_total"] == "0.04"
