"""Typed search domain models with construction-time validation.

Stage 1 of docs/search-rebuild-implementation-plan.md: an invalid object
cannot exist, so an invalid object can never reach SearchService. All
dataclasses are frozen; every field is validated in __post_init__ and a
violation raises SearchQueryValidationError naming the offending field.

Reversed ranges are an error at construction time. The parser/normalizer
(stage 4/5) repairs LLM output *before* construction with the
normalize_*_range() helpers, which swap the bounds and return the Polish
warning expected by the evaluation fixture (edge-04/edge-05 in
tests/fixtures/search_query_cases.json).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, fields
from datetime import date, datetime
from enum import Enum

from library.models.stalker_document_type import StalkerDocumentType

MIN_SUBJECT_YEAR = -10000
MAX_SUBJECT_YEAR = 3000
MAX_SEARCH_LIMIT = 100
MAX_QUERY_LENGTH = 1000
MAX_NAME_LENGTH = 300
MAX_TEXT_LENGTH = 1000
MAX_COMMENT_LENGTH = 2000

_LANGUAGE_RE = re.compile(r"^[a-z]{2,3}$")
_DOMAIN_RE = re.compile(r"^(?=.{4,253}$)([a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}$")

VALID_DOCUMENT_TYPES = frozenset(member.name for member in StalkerDocumentType)


class SearchQueryValidationError(ValueError):
    """Invalid value for a search domain object; `field` names the culprit."""

    def __init__(self, field_name: str, message: str):
        self.field = field_name
        super().__init__(f"{field_name}: {message}")


class SearchSort(str, Enum):
    RELEVANCE = "relevance"
    PUBLISHED_DESC = "published_desc"
    PUBLISHED_ASC = "published_asc"
    INGESTED_DESC = "ingested_desc"


class InterpretationStatus(str, Enum):
    PARSED = "parsed"
    AMBIGUOUS = "ambiguous"
    INVALID_JSON = "invalid_json"
    VALIDATION_ERROR = "validation_error"
    LLM_ERROR = "llm_error"
    FALLBACK = "fallback"


class FeedbackVerdict(str, Enum):
    CORRECT = "correct"
    PARTIALLY_CORRECT = "partially_correct"
    INCORRECT = "incorrect"


class ModelConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# --- field validators -------------------------------------------------------
# Shared by SearchFilters, ParsedSearchQuery and SearchRequest so each rule
# lives in exactly one place. Validators return the canonical value to store.


def _opt_text(name: str, value, max_length: int = MAX_NAME_LENGTH) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise SearchQueryValidationError(name, f"expected str or None, got {type(value).__name__}")
    stripped = value.strip()
    if not stripped:
        raise SearchQueryValidationError(name, "must not be empty; use None instead")
    if len(stripped) > max_length:
        raise SearchQueryValidationError(name, f"longer than {max_length} characters")
    return stripped


def _required_text(name: str, value, max_length: int = MAX_TEXT_LENGTH) -> str:
    text = _opt_text(name, value, max_length)
    if text is None:
        raise SearchQueryValidationError(name, "is required")
    return text


def _opt_date(name: str, value) -> date | None:
    if value is None:
        return None
    # datetime is a subclass of date -- a published_on bound must be a plain date.
    if isinstance(value, datetime) or not isinstance(value, date):
        raise SearchQueryValidationError(name, f"expected datetime.date or None, got {type(value).__name__}")
    return value


def _opt_datetime(name: str, value) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise SearchQueryValidationError(name, f"expected datetime.datetime or None, got {type(value).__name__}")
    return value


def _opt_year(name: str, value) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise SearchQueryValidationError(name, f"expected int or None, got {type(value).__name__}")
    if not MIN_SUBJECT_YEAR <= value <= MAX_SUBJECT_YEAR:
        raise SearchQueryValidationError(name, f"must be within [{MIN_SUBJECT_YEAR}, {MAX_SUBJECT_YEAR}]")
    return value


def _int_in_range(name: str, value, minimum: int, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SearchQueryValidationError(name, f"expected int, got {type(value).__name__}")
    if value < minimum or (maximum is not None and value > maximum):
        bound = f">= {minimum}" if maximum is None else f"within [{minimum}, {maximum}]"
        raise SearchQueryValidationError(name, f"must be {bound}")
    return value


def _bool(name: str, value) -> bool:
    if not isinstance(value, bool):
        raise SearchQueryValidationError(name, f"expected bool, got {type(value).__name__}")
    return value


def _str_tuple(name: str, value, max_item_length: int = MAX_TEXT_LENGTH) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise SearchQueryValidationError(name, f"expected a list of str, got {type(value).__name__}")
    items = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise SearchQueryValidationError(name, "every item must be a non-empty str")
        if len(item) > max_item_length:
            raise SearchQueryValidationError(name, f"item longer than {max_item_length} characters")
        items.append(item.strip())
    return tuple(items)


def _document_types(name: str, value) -> tuple[str, ...]:
    items = _str_tuple(name, value)
    for item in items:
        if item not in VALID_DOCUMENT_TYPES:
            allowed = ", ".join(sorted(VALID_DOCUMENT_TYPES))
            raise SearchQueryValidationError(name, f"unknown document type {item!r}; allowed: {allowed}")
    return items


def _languages(name: str, value) -> tuple[str, ...]:
    items = tuple(item.lower() for item in _str_tuple(name, value))
    for item in items:
        if not _LANGUAGE_RE.match(item):
            raise SearchQueryValidationError(name, f"invalid language code {item!r} (expected e.g. 'pl', 'en')")
    return items


def _opt_domain(name: str, value) -> str | None:
    text = _opt_text(name, value)
    if text is None:
        return None
    text = text.lower()
    if not _DOMAIN_RE.match(text):
        raise SearchQueryValidationError(name, f"invalid domain {text!r}")
    return text


def _enum(name: str, value, enum_cls):
    if isinstance(value, enum_cls):
        return value
    if isinstance(value, str):
        try:
            return enum_cls(value)
        except ValueError:
            pass
    allowed = ", ".join(member.value for member in enum_cls)
    raise SearchQueryValidationError(name, f"expected one of: {allowed}")


def _ordered(name_from: str, value_from, value_to) -> None:
    if value_from is not None and value_to is not None and value_from > value_to:
        raise SearchQueryValidationError(
            name_from, f"reversed range: {value_from} > {value_to} (normalize before constructing)"
        )


# --- range normalization (for the stage 4/5 parser, before construction) ----


def normalize_year_range(start: int | None, end: int | None) -> tuple[int | None, int | None, str | None]:
    """Swap a reversed year range; the warning is None when nothing changed."""
    if start is not None and end is not None and start > end:
        return end, start, f"Odwrócony zakres lat: zamieniono {start} i {end}."
    return start, end, None


def normalize_date_range(
    date_from: date | None, date_to: date | None
) -> tuple[date | None, date | None, str | None]:
    """Swap a reversed publication-date range; warning is None when unchanged."""
    if date_from is not None and date_to is not None and date_from > date_to:
        return date_to, date_from, f"Odwrócony zakres dat: zamieniono {date_from.isoformat()} i {date_to.isoformat()}."
    return date_from, date_to, None


def normalize_datetime_range(
    dt_from: datetime | None, dt_to: datetime | None
) -> tuple[datetime | None, datetime | None, str | None]:
    """Swap a reversed ingested-at range; warning is None when unchanged."""
    if dt_from is not None and dt_to is not None and dt_from > dt_to:
        return dt_to, dt_from, f"Odwrócony zakres dat: zamieniono {dt_from.isoformat()} i {dt_to.isoformat()}."
    return dt_from, dt_to, None


# --- domain objects ---------------------------------------------------------


@dataclass(frozen=True)
class SearchFilters:
    """Explicit, already-validated search constraints (no LLM involved)."""

    author_name: str | None = None
    publisher_name: str | None = None
    publisher_domain: str | None = None
    discovery_source_name: str | None = None
    collection_name: str | None = None
    published_on_from: date | None = None
    published_on_to: date | None = None
    ingested_at_from: datetime | None = None
    ingested_at_to: datetime | None = None
    subject_period_start_year: int | None = None
    subject_period_end_year: int | None = None
    document_types: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()

    def __post_init__(self):
        set_ = object.__setattr__
        set_(self, "author_name", _opt_text("author_name", self.author_name))
        set_(self, "publisher_name", _opt_text("publisher_name", self.publisher_name))
        set_(self, "publisher_domain", _opt_domain("publisher_domain", self.publisher_domain))
        set_(self, "discovery_source_name", _opt_text("discovery_source_name", self.discovery_source_name))
        set_(self, "collection_name", _opt_text("collection_name", self.collection_name))
        set_(self, "published_on_from", _opt_date("published_on_from", self.published_on_from))
        set_(self, "published_on_to", _opt_date("published_on_to", self.published_on_to))
        set_(self, "ingested_at_from", _opt_datetime("ingested_at_from", self.ingested_at_from))
        set_(self, "ingested_at_to", _opt_datetime("ingested_at_to", self.ingested_at_to))
        set_(self, "subject_period_start_year", _opt_year("subject_period_start_year", self.subject_period_start_year))
        set_(self, "subject_period_end_year", _opt_year("subject_period_end_year", self.subject_period_end_year))
        set_(self, "document_types", _document_types("document_types", self.document_types))
        set_(self, "languages", _languages("languages", self.languages))
        _ordered("published_on_from", self.published_on_from, self.published_on_to)
        _ordered("ingested_at_from", self.ingested_at_from, self.ingested_at_to)
        _ordered("subject_period_start_year", self.subject_period_start_year, self.subject_period_end_year)

    def is_empty(self) -> bool:
        return all(getattr(self, f.name) in (None, ()) for f in fields(self))


@dataclass(frozen=True)
class ParsedSearchQuery:
    """Validated interpretation of a natural-language query (plan section 5).

    Flat on purpose -- it mirrors the JSON contract the LLM produces.
    interpretation_summary is always required (the frontend shows it); apart
    from that, an object with no query, no filters and no clarification is
    legal and means "list everything".
    """

    query: str | None = None
    author_name: str | None = None
    publisher_name: str | None = None
    publisher_domain: str | None = None
    discovery_source_name: str | None = None
    collection_name: str | None = None
    published_on_from: date | None = None
    published_on_to: date | None = None
    ingested_at_from: datetime | None = None
    ingested_at_to: datetime | None = None
    subject_period_start_year: int | None = None
    subject_period_end_year: int | None = None
    temporal_expression: str | None = None
    document_types: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()
    sort: SearchSort = SearchSort.RELEVANCE
    interpretation_summary: str = ""
    warnings: tuple[str, ...] = ()
    clarification_required: bool = False
    clarification_question: str | None = None
    model_confidence: ModelConfidence = ModelConfidence.MEDIUM

    def __post_init__(self):
        set_ = object.__setattr__
        set_(self, "query", _opt_text("query", self.query, MAX_QUERY_LENGTH))
        # Reuse SearchFilters for every shared constraint field: same rules,
        # same error messages, single source of truth.
        filters = self.to_filters()
        for f in fields(SearchFilters):
            set_(self, f.name, getattr(filters, f.name))
        set_(self, "temporal_expression", _opt_text("temporal_expression", self.temporal_expression, MAX_TEXT_LENGTH))
        set_(self, "sort", _enum("sort", self.sort, SearchSort))
        set_(self, "interpretation_summary", _required_text("interpretation_summary", self.interpretation_summary))
        set_(self, "warnings", _str_tuple("warnings", self.warnings))
        set_(self, "clarification_required", _bool("clarification_required", self.clarification_required))
        set_(self, "clarification_question",
             _opt_text("clarification_question", self.clarification_question, MAX_TEXT_LENGTH))
        set_(self, "model_confidence", _enum("model_confidence", self.model_confidence, ModelConfidence))
        if self.clarification_question is not None and not self.clarification_required:
            raise SearchQueryValidationError(
                "clarification_question", "set while clarification_required is False"
            )

    def to_filters(self) -> SearchFilters:
        return SearchFilters(**{f.name: getattr(self, f.name) for f in fields(SearchFilters)})


@dataclass(frozen=True)
class SearchRequest:
    """One of two variants (plan section 4): natural language or explicit.

    Either `natural_query` alone (the LLM will interpret it), or an explicit
    `query`/`filters` combination that skips the LLM entirely. Mixing the two
    or providing neither is an error; an all-empty request must never reach
    the LLM (fixture case edge-06).
    """

    natural_query: str | None = None
    query: str | None = None
    filters: SearchFilters = field(default_factory=SearchFilters)
    limit: int = 10
    offset: int = 0
    sort: SearchSort = SearchSort.RELEVANCE

    def __post_init__(self):
        set_ = object.__setattr__
        set_(self, "natural_query", _opt_text("natural_query", self.natural_query, MAX_QUERY_LENGTH))
        set_(self, "query", _opt_text("query", self.query, MAX_QUERY_LENGTH))
        if not isinstance(self.filters, SearchFilters):
            raise SearchQueryValidationError("filters", f"expected SearchFilters, got {type(self.filters).__name__}")
        set_(self, "limit", _int_in_range("limit", self.limit, 1, MAX_SEARCH_LIMIT))
        set_(self, "offset", _int_in_range("offset", self.offset, 0))
        set_(self, "sort", _enum("sort", self.sort, SearchSort))
        explicit = self.query is not None or not self.filters.is_empty()
        if self.natural_query is not None and explicit:
            raise SearchQueryValidationError(
                "natural_query", "provide either natural_query or explicit query/filters, not both"
            )
        if self.natural_query is None and not explicit:
            raise SearchQueryValidationError("natural_query", "empty request: no query and no filters")

    @property
    def is_natural(self) -> bool:
        return self.natural_query is not None


@dataclass(frozen=True)
class SearchFeedback:
    """User verdict on an interpretation (POST /search/{id}/feedback)."""

    verdict: FeedbackVerdict
    comment: str | None = None
    corrected_query: ParsedSearchQuery | None = None

    def __post_init__(self):
        set_ = object.__setattr__
        set_(self, "verdict", _enum("verdict", self.verdict, FeedbackVerdict))
        set_(self, "comment", _opt_text("comment", self.comment, MAX_COMMENT_LENGTH))
        if self.corrected_query is not None and not isinstance(self.corrected_query, ParsedSearchQuery):
            raise SearchQueryValidationError(
                "corrected_query", f"expected ParsedSearchQuery, got {type(self.corrected_query).__name__}"
            )
