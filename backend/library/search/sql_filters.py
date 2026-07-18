"""Shared SQL filter builder for lexical and vector search (stage 6 of the plan).

``build_document_filters()`` turns a validated ``SearchFilters`` (stage 1)
into SQLAlchemy predicates against ``WebDocument`` columns — including a
correlated EXISTS subquery against ``document_time_periods`` for
``subject_period_*``. Both ``search_text()`` and ``get_similar()``
(``library/stalker_web_documents_db_postgresql.py``) apply the *same* list
via ``.where(*conditions)`` before ``LIMIT``, which is the stage 6
acceptance criterion: lexical and vector search use identical constraints.

Author/publisher/discovery-source filters need free-text-to-identifier
resolution (stage 7 — not built yet); passing one here raises
``NotImplementedError`` rather than silently searching unfiltered, which
would be a much worse failure mode than a loud one caught in review.
"""

from __future__ import annotations

from sqlalchemy import ColumnElement, exists, or_, select

from library.db.models import DocumentTimePeriod, WebDocument
from library.search.types import SearchFilters

_UNRESOLVED_NAME_FIELDS = ("author_name", "publisher_name", "publisher_domain", "discovery_source_name")


def build_document_filters(filters: SearchFilters) -> list[ColumnElement[bool]]:
    """Return WebDocument-scoped predicates for the given filters.

    Every returned element is meant to be combined with AND (via
    ``.where(*conditions)`` or ``and_(*conditions)``) against a query that
    already selects from/joins ``WebDocument``.
    """
    for field_name in _UNRESOLVED_NAME_FIELDS:
        if getattr(filters, field_name) is not None:
            raise NotImplementedError(
                f"{field_name} filtering requires name resolution (stage 7 of "
                "docs/search-rebuild-implementation-plan.md); not yet supported by "
                "build_document_filters()"
            )

    conditions: list[ColumnElement[bool]] = []

    if filters.collection_name is not None:
        # Today collection_name maps onto the plain web_documents.project
        # string column (ADR-017: project is 100% NULL, kept as the future
        # 1:N collection_id) — an exact match, not a lookup-table resolution
        # like author/publisher, so it's safe to filter on directly now.
        conditions.append(WebDocument.project == filters.collection_name)

    if filters.published_on_from is not None:
        conditions.append(WebDocument.date_from >= filters.published_on_from)
    if filters.published_on_to is not None:
        conditions.append(WebDocument.date_from <= filters.published_on_to)

    if filters.ingested_at_from is not None:
        conditions.append(WebDocument.created_at >= filters.ingested_at_from)
    if filters.ingested_at_to is not None:
        conditions.append(WebDocument.created_at <= filters.ingested_at_to)

    if filters.document_types:
        conditions.append(WebDocument.document_type.in_(filters.document_types))

    if filters.languages:
        conditions.append(WebDocument.language.in_(filters.languages))

    if filters.subject_period_start_year is not None or filters.subject_period_end_year is not None:
        conditions.append(_subject_period_overlap(
            filters.subject_period_start_year, filters.subject_period_end_year,
        ))

    return conditions


def _subject_period_overlap(start_year: int | None, end_year: int | None) -> ColumnElement[bool]:
    """EXISTS a classified document_time_periods row overlapping [start_year, end_year].

    A missing bound on either side (the filter or the stored row) is
    open-ended, so a label-only period ("starozytnosc" with no years) never
    disqualifies its document — the same semantics the pre-stage-6
    Python-side filter used, now evaluated in SQL, before LIMIT, for both
    lexical and vector search.
    """
    subquery = select(DocumentTimePeriod.id).where(DocumentTimePeriod.document_id == WebDocument.id)
    if start_year is not None:
        subquery = subquery.where(or_(
            DocumentTimePeriod.period_end_year.is_(None),
            DocumentTimePeriod.period_end_year >= start_year,
        ))
    if end_year is not None:
        subquery = subquery.where(or_(
            DocumentTimePeriod.period_start_year.is_(None),
            DocumentTimePeriod.period_start_year <= end_year,
        ))
    return exists(subquery)
