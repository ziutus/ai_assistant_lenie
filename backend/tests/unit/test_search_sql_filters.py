"""Tests for library/search/sql_filters.py (stage 6 of the search rebuild).

No live database: conditions are inspected by compiling them to SQL text
(the established convention in this test suite — see
test_similarity_search_orm.py) and by their number/emptiness.
"""

import datetime

import pytest

pytest.importorskip("sqlalchemy")

from library.search.sql_filters import build_document_filters  # noqa: E402
from library.search.types import SearchFilters  # noqa: E402


def compiled(condition) -> str:
    return str(condition.compile(compile_kwargs={"literal_binds": True}))


class TestEmptyFilters:
    def test_empty_filters_yield_no_conditions(self):
        assert build_document_filters(SearchFilters()) == []


class TestCollectionName:
    def test_maps_to_web_documents_project_exact_match(self):
        conditions = build_document_filters(SearchFilters(collection_name="lenie"))
        assert len(conditions) == 1
        sql = compiled(conditions[0])
        assert "project" in sql.lower()
        assert "lenie" in sql


class TestPublishedOn:
    def test_from_only(self):
        conditions = build_document_filters(SearchFilters(published_on_from=datetime.date(2020, 1, 1)))
        assert len(conditions) == 1
        sql = compiled(conditions[0])
        assert "date_from" in sql.lower()
        assert ">=" in sql

    def test_to_only(self):
        conditions = build_document_filters(SearchFilters(published_on_to=datetime.date(2020, 12, 31)))
        assert len(conditions) == 1
        assert "<=" in compiled(conditions[0])

    def test_from_and_to_produce_two_conditions(self):
        conditions = build_document_filters(SearchFilters(
            published_on_from=datetime.date(2020, 1, 1), published_on_to=datetime.date(2020, 12, 31),
        ))
        assert len(conditions) == 2


class TestIngestedAt:
    def test_from_only(self):
        conditions = build_document_filters(
            SearchFilters(ingested_at_from=datetime.datetime(2020, 1, 1, 0, 0)),
        )
        assert len(conditions) == 1
        sql = compiled(conditions[0])
        assert "created_at" in sql.lower()
        assert ">=" in sql

    def test_to_only(self):
        conditions = build_document_filters(
            SearchFilters(ingested_at_to=datetime.datetime(2020, 12, 31, 23, 59)),
        )
        assert "<=" in compiled(conditions[0])


class TestDocumentTypesAndLanguages:
    def test_document_types_in_clause(self):
        conditions = build_document_filters(SearchFilters(document_types=("webpage", "youtube")))
        assert len(conditions) == 1
        sql = compiled(conditions[0])
        assert "document_type" in sql.lower()
        assert "webpage" in sql
        assert "youtube" in sql

    def test_languages_in_clause(self):
        conditions = build_document_filters(SearchFilters(languages=("pl", "en")))
        assert len(conditions) == 1
        sql = compiled(conditions[0])
        assert "language" in sql.lower()
        assert "'pl'" in sql
        assert "'en'" in sql


class TestSubjectPeriod:
    def test_start_year_only_produces_exists_subquery(self):
        conditions = build_document_filters(SearchFilters(subject_period_start_year=1939))
        assert len(conditions) == 1
        sql = compiled(conditions[0])
        assert "EXISTS" in sql
        assert "document_time_periods" in sql
        assert "1939" in sql

    def test_end_year_only(self):
        conditions = build_document_filters(SearchFilters(subject_period_end_year=1945))
        sql = compiled(conditions[0])
        assert "EXISTS" in sql
        assert "1945" in sql

    def test_both_bounds_correlated_on_web_document_id(self):
        conditions = build_document_filters(
            SearchFilters(subject_period_start_year=1939, subject_period_end_year=1945),
        )
        assert len(conditions) == 1
        sql = compiled(conditions[0])
        assert "web_documents.id" in sql
        assert "document_time_periods.document_id" in sql

    def test_open_ended_stored_row_matches_via_or_is_null(self):
        conditions = build_document_filters(SearchFilters(subject_period_start_year=1939))
        sql = compiled(conditions[0])
        assert "period_end_year IS NULL" in sql


class TestAuthorAndDiscoverySourceFilters:
    def test_author_uses_role_canonical_name_and_alias(self):
        sql = compiled(build_document_filters(SearchFilters(author_name="Jan Kowalski"))[0])
        assert "document_persons.role = 'author'" in sql
        assert "persons.canonical_name" in sql
        assert "person_aliases.alias" in sql
        assert "jan kowalski" in sql

    def test_author_fallback_uses_byline_only_without_structured_author(self):
        sql = compiled(build_document_filters(SearchFilters(author_name="Jan Kowalski"))[0])
        assert "NOT (EXISTS" in sql
        assert "web_documents.author" in sql
        assert "LIKE" in sql

    def test_discovery_source_uses_sources_not_information_sources(self):
        sql = compiled(build_document_filters(SearchFilters(discovery_source_name="Unknow.News"))[0])
        assert "web_documents.source IN" in sql
        assert "FROM sources" in sql
        assert "information_sources" not in sql
        assert "unknow.news" in sql


class TestPublisherFilters:
    def test_name_uses_all_matching_publisher_ids(self):
        sql = compiled(build_document_filters(SearchFilters(publisher_name="Onet.pl"))[0])
        assert "web_documents.publisher_id IN" in sql
        assert "SELECT publishers.id" in sql
        assert "unaccent(lower(publishers.canonical_name))" in sql
        assert "onet.pl" in sql

    def test_domain_uses_unique_domain_mapping(self):
        sql = compiled(build_document_filters(SearchFilters(publisher_domain="Onet.PL"))[0])
        assert "web_documents.publisher_id IN" in sql
        assert "publisher_domains.publisher_id" in sql
        assert "lower(publisher_domains.domain)" in sql
        assert "onet.pl" in sql


class TestCombinedFilters:
    def test_multiple_filters_combine_to_multiple_conditions(self):
        conditions = build_document_filters(SearchFilters(
            collection_name="lenie",
            document_types=("webpage",),
            languages=("pl",),
            subject_period_start_year=1939,
            subject_period_end_year=1945,
        ))
        assert len(conditions) == 4

    def test_conditions_apply_cleanly_to_a_where_clause(self):
        from sqlalchemy import select

        from library.db.models import WebDocument

        conditions = build_document_filters(SearchFilters(
            collection_name="lenie", document_types=("webpage",),
        ))
        stmt = select(WebDocument.id).where(*conditions)
        sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "web_documents.project" in sql
        assert "web_documents.document_type" in sql
