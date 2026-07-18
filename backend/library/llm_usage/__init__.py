"""Central LLM usage and cost accounting (search-rebuild plan, stages 2-3).

Stage 2 ships the pricing math (`pricing.py`) and the audit tables
(search_interpretation_logs, llm_pricing, llm_usage_logs — see
library/db/models.py). Stage 3 adds the service that writes one
llm_usage_logs record per LLM call; domain modules must never compute
costs themselves.
"""

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
    "estimate_cost",
]
