"""Tests for WebsitesDBPostgreSQL.list_by_filters() (stage 6 session B).

Filter-only document listing: no text query, no embedding. No live
database: statements are compiled to SQL text via the session-mock
convention already used in test_similarity_search_orm.py.
"""

from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")

from library.search.types import SearchFilters, SearchSort  # noqa: E402
from library.stalker_web_documents_db_postgresql import WebsitesDBPostgreSQL  # noqa: E402


def _repo_with_mock_session(rows=None):
    session = MagicMock()
    session.scalars.return_value.all.return_value = rows or []
    return WebsitesDBPostgreSQL(session=session), session


def _compiled_sql(session) -> str:
    stmt = session.scalars.call_args[0][0]
    return str(stmt.compile(compile_kwargs={"literal_binds": True}))


def _fake_document(**overrides):
    doc = MagicMock()
    defaults = {
        "id": 1, "title": "Tytuł", "url": "https://example.com", "document_type": "webpage",
        "project": None, "language": "pl", "date_from": None, "created_at": None,
    }
    defaults.update(overrides)
    for key, value in defaults.items():
        setattr(doc, key, value)
    return doc


class TestListByFiltersEmptyFilters:
    def test_empty_filters_lists_everything(self):
        repo, session = _repo_with_mock_session([_fake_document()])
        result = repo.list_by_filters(SearchFilters())
        assert len(result) == 1
        session.scalars.assert_called_once()

    def test_empty_filters_produce_no_where_clause(self):
        repo, session = _repo_with_mock_session()
        repo.list_by_filters(SearchFilters())
        sql = _compiled_sql(session)
        assert "WHERE" not in sql


class TestListByFiltersApplied:
    def test_document_type_filter_applied(self):
        repo, session = _repo_with_mock_session()
        repo.list_by_filters(SearchFilters(document_types=("webpage",)))
        sql = _compiled_sql(session)
        assert "web_documents.document_type IN" in sql
        assert "'webpage'" in sql

    def test_subject_period_filter_applied(self):
        repo, session = _repo_with_mock_session()
        repo.list_by_filters(SearchFilters(subject_period_start_year=1939, subject_period_end_year=1945))
        sql = _compiled_sql(session)
        assert "EXISTS" in sql
        assert "document_time_periods" in sql

    def test_filter_applied_before_limit(self):
        repo, session = _repo_with_mock_session()
        repo.list_by_filters(SearchFilters(document_types=("webpage",)), limit=7)
        sql = _compiled_sql(session)
        assert sql.index("document_type") < sql.index("LIMIT")

    def test_author_name_filter_is_applied(self):
        repo, session = _repo_with_mock_session()
        repo.list_by_filters(SearchFilters(author_name="Jan Kowalski"))
        assert "document_persons.role = 'author'" in _compiled_sql(session)


class TestListByFiltersSort:
    def test_default_sort_is_newest_first_by_created_at(self):
        repo, session = _repo_with_mock_session()
        repo.list_by_filters(SearchFilters())
        sql = _compiled_sql(session)
        assert "web_documents.created_at DESC" in sql

    def test_published_desc(self):
        repo, session = _repo_with_mock_session()
        repo.list_by_filters(SearchFilters(), sort=SearchSort.PUBLISHED_DESC)
        sql = _compiled_sql(session)
        assert "web_documents.date_from DESC" in sql

    def test_published_asc(self):
        repo, session = _repo_with_mock_session()
        repo.list_by_filters(SearchFilters(), sort=SearchSort.PUBLISHED_ASC)
        sql = _compiled_sql(session)
        assert "web_documents.date_from ASC" in sql

    def test_ingested_desc(self):
        repo, session = _repo_with_mock_session()
        repo.list_by_filters(SearchFilters(), sort=SearchSort.INGESTED_DESC)
        sql = _compiled_sql(session)
        assert "web_documents.created_at DESC" in sql

    def test_relevance_falls_back_to_ingested_desc(self):
        repo, session = _repo_with_mock_session()
        repo.list_by_filters(SearchFilters(), sort=SearchSort.RELEVANCE)
        sql = _compiled_sql(session)
        assert "web_documents.created_at DESC" in sql

    def test_string_sort_value_accepted(self):
        repo, session = _repo_with_mock_session()
        repo.list_by_filters(SearchFilters(), sort="published_desc")
        sql = _compiled_sql(session)
        assert "web_documents.date_from DESC" in sql


class TestListByFiltersLimitOffset:
    def test_limit_and_offset_in_sql(self):
        repo, session = _repo_with_mock_session()
        repo.list_by_filters(SearchFilters(), limit=15, offset=30)
        sql = _compiled_sql(session)
        assert "LIMIT 15" in sql
        assert "OFFSET 30" in sql


class TestListByFiltersResultShape:
    def test_result_shape(self):
        import datetime

        doc = _fake_document(
            id=42, title="Artykuł", url="https://x.pl/a", document_type="webpage",
            project="lenie", language="pl",
            date_from=datetime.date(2020, 1, 1), created_at=datetime.datetime(2020, 1, 2, 10, 0),
        )
        repo, _ = _repo_with_mock_session([doc])
        result = repo.list_by_filters(SearchFilters())
        assert result == [{
            "website_id": 42,
            "title": "Artykuł",
            "url": "https://x.pl/a",
            "document_type": "webpage",
            "project": "lenie",
            "language": "pl",
            "date_from": "2020-01-01",
            "created_at": "2020-01-02T10:00:00",
            "similarity": None,
            "search_match": "filters_only",
        }]

    def test_null_dates_become_none(self):
        repo, _ = _repo_with_mock_session([_fake_document(date_from=None, created_at=None)])
        result = repo.list_by_filters(SearchFilters())
        assert result[0]["date_from"] is None
        assert result[0]["created_at"] is None

    def test_no_commit_called(self):
        repo, session = _repo_with_mock_session([_fake_document()])
        repo.list_by_filters(SearchFilters())
        session.commit.assert_not_called()
