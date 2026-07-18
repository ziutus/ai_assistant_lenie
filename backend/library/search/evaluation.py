"""Deterministic scoring for the real-model search parser evaluation corpus."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import date, datetime
from enum import Enum


def _json_value(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    return value


def parsed_query_dict(parsed_query) -> dict:
    """Convert ParsedSearchQuery to stable, JSON-compatible evaluation data."""
    return {key: _json_value(value) for key, value in asdict(parsed_query).items()}


def score_case(case: dict, result) -> dict:
    """Score only fields explicitly pinned by a fixture case."""
    actual = parsed_query_dict(result.parsed_query)
    comparisons = {
        field: {"expected": expected, "actual": actual.get(field), "correct": actual.get(field) == expected}
        for field, expected in case["expected"].items()
    }
    status = result.status.value if hasattr(result.status, "value") else str(result.status)
    if status in {"invalid_json", "validation_error", "llm_error"}:
        error_category = status
    elif all(item["correct"] for item in comparisons.values()):
        error_category = None
    else:
        error_category = "field_mismatch"
    usage = result.usage
    cost = getattr(usage, "cost", None)
    return {
        "id": case["id"],
        "category": case["category"],
        "natural_query": case["natural_query"],
        "status": status,
        "fallback_used": result.fallback_used,
        "valid_json": status not in {"invalid_json", "llm_error"},
        "all_expected_fields_correct": all(item["correct"] for item in comparisons.values()),
        "error_category": error_category,
        "fields": comparisons,
        "actual": actual,
        "latency_ms": result.llm_latency_ms,
        "usage_log_id": getattr(usage, "usage_log_id", None),
        "interpretation_log_id": result.interpretation_log_id,
        "prompt_tokens": getattr(usage, "prompt_tokens", None),
        "completion_tokens": getattr(usage, "completion_tokens", None),
        "total_tokens": getattr(usage, "total_tokens", None),
        "cost_amount": str(cost.total_cost) if cost and cost.total_cost is not None else None,
        "cost_currency": getattr(cost, "currency", None),
        "cost_status": getattr(getattr(cost, "status", None), "value", getattr(cost, "status", None)),
    }


def summarize(case_results: list[dict], *, skipped_cases: int = 0) -> dict:
    """Aggregate case, field, latency, token and same-currency cost metrics."""
    field_counts = defaultdict(Counter)
    for case in case_results:
        for field, comparison in case["fields"].items():
            field_counts[field]["evaluated"] += 1
            field_counts[field]["correct"] += int(comparison["correct"])
    per_field = {
        field: {
            "correct": counts["correct"],
            "evaluated": counts["evaluated"],
            "accuracy": counts["correct"] / counts["evaluated"],
        }
        for field, counts in sorted(field_counts.items())
    }
    latencies = [case["latency_ms"] for case in case_results if case["latency_ms"] is not None]
    tokens = [case["total_tokens"] for case in case_results if case["total_tokens"] is not None]
    costs = [case["cost_amount"] for case in case_results]
    currencies = {case["cost_currency"] for case in case_results if case["cost_currency"]}
    total_cost = None
    currency = None
    if costs and all(cost is not None for cost in costs) and len(currencies) == 1:
        from decimal import Decimal

        total_cost = str(sum(Decimal(cost) for cost in costs))
        currency = next(iter(currencies))
    count = len(case_results)
    correct = sum(case["all_expected_fields_correct"] for case in case_results)
    return {
        "fixture_cases": count + skipped_cases,
        "llm_calls": count,
        "skipped_cases": skipped_cases,
        "valid_json": sum(case["valid_json"] for case in case_results),
        "valid_json_rate": sum(case["valid_json"] for case in case_results) / count if count else 0,
        "fully_correct_cases": correct,
        "case_accuracy": correct / count if count else 0,
        "per_field": per_field,
        "error_categories": dict(sorted(Counter(case["error_category"] for case in case_results if case["error_category"]).items())),
        "latency_ms_total": sum(latencies) if len(latencies) == count else None,
        "latency_ms_average": sum(latencies) / count if len(latencies) == count and count else None,
        "tokens_total": sum(tokens) if len(tokens) == count else None,
        "tokens_average": sum(tokens) / count if len(tokens) == count and count else None,
        "cost_total": total_cost,
        "cost_currency": currency,
    }
