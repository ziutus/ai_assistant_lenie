"""Search domain types (stage 1 of docs/search-rebuild-implementation-plan.md).

Public surface of the new search subsystem. Types use the target domain
vocabulary (document_id, published_on, subject_period_*, discovery_source,
collection) from day one, regardless of the legacy SQL column names.
"""

import importlib

from library.search.temporal import (
    ANCHOR_DICTIONARY_VERSION,
    HISTORICAL_ANCHORS,
    TemporalRelation,
    TemporalRelationError,
    enrich_subject_period,
    resolve_anchor,
    resolve_relation,
)
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
    "ANCHOR_DICTIONARY_VERSION",
    "HISTORICAL_ANCHORS",
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
    "TemporalRelation",
    "TemporalRelationError",
    "delete_expired_interpretations",
    "enrich_subject_period",
    "normalize_date_range",
    "normalize_datetime_range",
    "normalize_year_range",
    "parsed_query_to_dict",
    "record_feedback",
    "record_interpretation",
    "resolve_anchor",
    "resolve_relation",
    "SearchQueryParseResult",
    "parse_search_query",
    "build_document_filters",
]

# audit_repository/parser/sql_filters need sqlalchemy (via ai.py or
# library.db.models); lazy re-export keeps `library.search` importable in
# the lightweight (uvx) test environment.
_AUDIT_EXPORTS = frozenset(
    {"record_interpretation", "record_feedback", "delete_expired_interpretations", "parsed_query_to_dict"}
)
_PARSER_EXPORTS = frozenset({"SearchQueryParseResult", "parse_search_query"})
_SQL_FILTER_EXPORTS = frozenset({"build_document_filters"})


def __getattr__(name):
    if name in _AUDIT_EXPORTS:
        return getattr(importlib.import_module("library.search.audit_repository"), name)
    if name in _PARSER_EXPORTS:
        return getattr(importlib.import_module("library.search.parser"), name)
    if name in _SQL_FILTER_EXPORTS:
        return getattr(importlib.import_module("library.search.sql_filters"), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
