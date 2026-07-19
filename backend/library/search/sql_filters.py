"""Shared SQL filter builder for lexical and vector search (stage 6 of the plan).

``build_document_filters()`` turns a validated ``SearchFilters`` (stage 1)
into SQLAlchemy predicates against ``Document`` columns — including a
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
    Collection,
    DiscoverySource,
    DocumentPerson,
    DocumentTimePeriod,
    Person,
    PersonAlias,
    Publisher,
    PublisherDomain,
    Document,
)
from library.publisher_registry import normalize_publisher_domain
from library.search.types import SearchFilters

def build_document_filters(filters: SearchFilters) -> list[ColumnElement[bool]]:
    """Return Document-scoped predicates for the given filters.

    Every returned element is meant to be combined with AND (via
    ``.where(*conditions)`` or ``and_(*conditions)``) against a query that
    already selects from/joins ``Document``.
    """
    conditions: list[ColumnElement[bool]] = []

    if filters.author_name is not None:
        conditions.append(_author_match(filters.author_name))

    if filters.publisher_name is not None:
        publisher_ids = select(Publisher.id).where(
            func.unaccent(func.lower(Publisher.canonical_name))
            == func.unaccent(filters.publisher_name.strip().lower()),
        )
        conditions.append(Document.publisher_id.in_(publisher_ids))

    if filters.publisher_domain is not None:
        domain = normalize_publisher_domain(filters.publisher_domain)
        publisher_ids = select(PublisherDomain.publisher_id).where(
            func.lower(PublisherDomain.domain) == domain,
        )
        conditions.append(Document.publisher_id.in_(publisher_ids))

    if filters.discovery_source_name is not None:
        # Stage 11d: documents carries discovery_source_id (FK to the
        # discovery_sources lookup); the filter still takes a NAME. Never
        # join information_sources (claim/reporting provenance).
        discovery_source_ids = select(DiscoverySource.id).where(
            func.unaccent(func.lower(DiscoverySource.name))
            == func.unaccent(filters.discovery_source_name.strip().lower()),
        )
        conditions.append(Document.discovery_source_id.in_(discovery_source_ids))

    if filters.collection_name is not None:
        # Stage 11c: collections is a real lookup table and documents
        # carries collection_id (ADR-017: 1:N). Exact name match resolved
        # through a subquery — an unknown collection name matches nothing.
        collection_ids = select(Collection.id).where(
            Collection.name == filters.collection_name,
        )
        conditions.append(Document.collection_id.in_(collection_ids))

    if filters.published_on_from is not None:
        conditions.append(Document.published_on >= filters.published_on_from)
    if filters.published_on_to is not None:
        conditions.append(Document.published_on <= filters.published_on_to)

    if filters.ingested_at_from is not None:
        conditions.append(Document.created_at >= filters.ingested_at_from)
    if filters.ingested_at_to is not None:
        conditions.append(Document.created_at <= filters.ingested_at_to)

    if filters.document_types:
        conditions.append(Document.document_type.in_(filters.document_types))

    if filters.languages:
        conditions.append(Document.language.in_(filters.languages))

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
        DocumentPerson.document_id == Document.id,
        DocumentPerson.role == "author",
    )
    matching_link = (
        select(DocumentPerson.id)
        .join(Person, DocumentPerson.person_id == Person.id)
        .outerjoin(PersonAlias, PersonAlias.person_id == Person.id)
        .where(
            DocumentPerson.document_id == Document.id,
            DocumentPerson.role == "author",
            or_(
                func.unaccent(func.lower(Person.canonical_name)) == func.unaccent(folded),
                func.unaccent(func.lower(PersonAlias.alias)) == func.unaccent(folded),
            ),
        )
    )
    legacy_byline = func.unaccent(func.lower(func.coalesce(Document.byline, ""))).ilike(
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
    subquery = select(DocumentTimePeriod.id).where(DocumentTimePeriod.document_id == Document.id)
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
