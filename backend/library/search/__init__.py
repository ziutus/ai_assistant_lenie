"""Search domain types (stage 1 of docs/search-rebuild-implementation-plan.md).

Public surface of the new search subsystem. Types use the target domain
vocabulary (document_id, published_on, subject_period_*, discovery_source,
collection) from day one, regardless of the legacy SQL column names.
"""

from library.search.types import (
    MAX_SEARCH_LIMIT,
    MAX_SUBJECT_YEAR,
    MIN_SUBJECT_YEAR,
    FeedbackVerdict,
    InterpretationStatus,
    ModelConfidence,
    ParsedSearchQuery,
    SearchFeedback,
    SearchFilters,
    SearchQueryValidationError,
    SearchRequest,
    SearchSort,
    normalize_date_range,
    normalize_datetime_range,
    normalize_year_range,
)

__all__ = [
    "MAX_SEARCH_LIMIT",
    "MAX_SUBJECT_YEAR",
    "MIN_SUBJECT_YEAR",
    "FeedbackVerdict",
    "InterpretationStatus",
    "ModelConfidence",
    "ParsedSearchQuery",
    "SearchFeedback",
    "SearchFilters",
    "SearchQueryValidationError",
    "SearchRequest",
    "SearchSort",
    "normalize_date_range",
    "normalize_datetime_range",
    "normalize_year_range",
]
