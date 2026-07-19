"""Shared SQL filter builder for lexical and vector search (stage 6 of the plan).

``build_document_filters()`` turns a validated ``SearchFilters`` (stage 1)
into SQLAlchemy predicates against ``WebDocument`` columns — including a
correlated EXISTS subquery against ``document_time_periods`` for
``subject_period_*``. Both ``search_text()`` and ``get_similar()``
(``library/stalker_web_documents_db_postgresql.py``) apply the *same* list
via ``.where(*conditions)`` before ``LIMIT``, which is the stage 6
acceptance criterion: lexical and vector search use identical constraints.

Stage 7 adds deterministic name filters: publisher ids through the publisher
registry, authors through role='author' person/alias links with a guarded
legacy byline fallback, and discovery sources through the physical
``sources`` lookup. None of these paths chooses an arbitrary first match.
"""

from __future__ import annotations

from sqlalchemy import ColumnElement, and_, exists, func, or_, select

from library.db.models import (
    DocumentPerson,
    DocumentTimePeriod,
    Person,
    PersonAlias,
    Publisher,
    PublisherDomain,
    Source,
    WebDocument,
)
from library.publisher_registry import normalize_publisher_domain
from library.search.types import SearchFilters

def build_document_filters(filters: SearchFilters) -> list[ColumnElement[bool]]:
    """Return WebDocument-scoped predicates for the given filters.

    Every returned element is meant to be combined with AND (via
    ``.where(*conditions)`` or ``and_(*conditions)``) against a query that
    already selects from/joins ``WebDocument``.
    """
    conditions: list[ColumnElement[bool]] = []

    if filters.author_name is not None:
        conditions.append(_author_match(filters.author_name))

    if filters.publisher_name is not None:
        publisher_ids = select(Publisher.id).where(
            func.unaccent(func.lower(Publisher.canonical_name))
            == func.unaccent(filters.publisher_name.strip().lower()),
        )
        conditions.append(WebDocument.publisher_id.in_(publisher_ids))

    if filters.publisher_domain is not None:
        domain = normalize_publisher_domain(filters.publisher_domain)
        publisher_ids = select(PublisherDomain.publisher_id).where(
            func.lower(PublisherDomain.domain) == domain,
        )
        conditions.append(WebDocument.publisher_id.in_(publisher_ids))

    if filters.discovery_source_name is not None:
        # Physical names stay ``source``/``sources`` until stage 11, but the
        # domain meaning here is explicitly the discovery channel.  Never
        # join information_sources (claim/reporting provenance).
        discovery_source_names = select(Source.name).where(
            func.unaccent(func.lower(Source.name))
            == func.unaccent(filters.discovery_source_name.strip().lower()),
        )
        conditions.append(WebDocument.source.in_(discovery_source_names))

    if filters.collection_name is not None:
        # Today collection_name maps onto the plain web_documents.project
        # string column (ADR-017: project is 100% NULL, kept as the future
        # 1:N collection_id) — an exact match, not a lookup-table resolution
        # like author/publisher, so it's safe to filter on directly now.
        conditions.append(WebDocument.project == filters.collection_name)

    if filters.published_on_from is not None:
        conditions.append(WebDocument.published_on >= filters.published_on_from)
    if filters.published_on_to is not None:
        conditions.append(WebDocument.published_on <= filters.published_on_to)

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


def _author_match(name: str) -> ColumnElement[bool]:
    """Structured author/alias match with legacy byline fallback only.

    The fallback is used only when a document has no role='author' links, so
    stale display text can never override normalized authorship.
    """
    folded = name.strip().lower()
    author_links = select(DocumentPerson.id).where(
        DocumentPerson.document_id == WebDocument.id,
        DocumentPerson.role == "author",
    )
    matching_link = (
        select(DocumentPerson.id)
        .join(Person, DocumentPerson.person_id == Person.id)
        .outerjoin(PersonAlias, PersonAlias.person_id == Person.id)
        .where(
            DocumentPerson.document_id == WebDocument.id,
            DocumentPerson.role == "author",
            or_(
                func.unaccent(func.lower(Person.canonical_name)) == func.unaccent(folded),
                func.unaccent(func.lower(PersonAlias.alias)) == func.unaccent(folded),
            ),
        )
    )
    legacy_byline = func.unaccent(func.lower(func.coalesce(WebDocument.byline, ""))).ilike(
        func.unaccent(f"%{folded}%"),
    )
    return or_(exists(matching_link), and_(~exists(author_links), legacy_byline))


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
