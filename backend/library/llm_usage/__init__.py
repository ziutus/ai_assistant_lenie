"""Central LLM usage and cost accounting (search-rebuild plan, stages 2-3).

Stage 2 ships the pricing math (`pricing.py`), the audit tables
(search_interpretation_logs, llm_pricing, llm_usage_logs — see
library/db/models.py) and the central recorder (`recorder.py`) that writes
exactly one llm_usage_logs record per LLM call. Stage 3 wires the recorder
into ai.py; domain modules must never compute costs themselves.
"""

import importlib

from library.llm_usage.pricing import (
    UNKNOWN_COST,
    CostEstimate,
    CostStatus,
    PricingError,
    PricingMode,
    estimate_cost,
)

__all__ = [
    "UNKNOWN_COST",
    "CostEstimate",
    "CostStatus",
    "PricingError",
    "PricingMode",
    "UsageRecord",
    "estimate_cost",
    "record_llm_usage",
]

# recorder needs sqlalchemy; lazy re-export keeps `library.llm_usage`
# importable in the lightweight (uvx) test environment without it.
_RECORDER_EXPORTS = frozenset({"UsageRecord", "record_llm_usage"})


def __getattr__(name):
    if name in _RECORDER_EXPORTS:
        return getattr(importlib.import_module("library.llm_usage.recorder"), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
