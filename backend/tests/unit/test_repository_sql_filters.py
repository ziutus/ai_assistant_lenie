"""Tests that search_text() and get_similar() share identical filter
constraints, applied before LIMIT (stage 6 acceptance criterion).

No live database: statements are compiled to SQL text via the session-mock
convention already used in test_similarity_search_orm.py.
"""

from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")

from library.search.types import SearchFilters  # noqa: E402
from library.stalker_web_documents_db_postgresql import WebsitesDBPostgreSQL  # noqa: E402


def _repo_with_mock_session():
    session = MagicMock()
    session.execute.return_value.all.return_value = []
    session.scalars.return_value.all.return_value = []
    return WebsitesDBPostgreSQL(session=session), session


def _compiled_sql(session) -> str:
    stmt = session.execute.call_args[0][0] if session.execute.called else session.scalars.call_args[0][0]
    return str(stmt.compile(compile_kwargs={"literal_binds": True}))


FILTERS = SearchFilters(
    document_types=("webpage",),
    languages=("pl",),
    subject_period_start_year=1939,
    subject_period_end_year=1945,
)


class TestGetSimilarFilters:
    def test_filters_none_by_default_no_extra_predicates(self):
        repo, session = _repo_with_mock_session()
        repo.get_similar([0.1, 0.2], model="m")
        sql = _compiled_sql(session)
        assert "document_type IN" not in sql
        assert "EXISTS" not in sql

    def test_filters_applied_to_where_clause(self):
        repo, session = _repo_with_mock_session()
        repo.get_similar([0.1, 0.2], model="m", filters=FILTERS)
        sql = _compiled_sql(session)
        assert "documents.document_type" in sql
        assert "'webpage'" in sql
        assert "documents.language" in sql
        assert "'pl'" in sql
        assert "EXISTS" in sql
        assert "document_time_periods" in sql

    def test_filters_applied_before_limit(self):
        repo, session = _repo_with_mock_session()
        repo.get_similar([0.1, 0.2], model="m", limit=7, filters=FILTERS)
        sql = _compiled_sql(session)
        assert sql.index("document_type") < sql.index("LIMIT")

    def test_collection_and_filters_combine(self):
        from dataclasses import replace
        repo, session = _repo_with_mock_session()
        repo.get_similar([0.1, 0.2], model="m",
                         filters=replace(FILTERS, collection_name="lenie"))
        sql = _compiled_sql(session)
        assert "documents.collection_id" in sql
        assert "collections" in sql
        assert "'lenie'" in sql
        assert "document_type" in sql


class TestSearchTextFilters:
    def test_filters_none_by_default_no_extra_predicates(self):
        repo, session = _repo_with_mock_session()
        repo.search_text("wojna")
        sql = _compiled_sql(session)
        assert "document_type IN" not in sql
        assert "EXISTS" not in sql

    def test_filters_applied_to_where_clause(self):
        repo, session = _repo_with_mock_session()
        repo.search_text("wojna", filters=FILTERS)
        sql = _compiled_sql(session)
        assert "documents.document_type" in sql
        assert "'webpage'" in sql
        assert "documents.language" in sql
        assert "'pl'" in sql
        assert "EXISTS" in sql
        assert "document_time_periods" in sql

    def test_filters_applied_before_limit(self):
        repo, session = _repo_with_mock_session()
        repo.search_text("wojna", limit=7, filters=FILTERS)
        sql = _compiled_sql(session)
        assert sql.index("document_type") < sql.index("LIMIT")

    def test_empty_query_short_circuits_before_filters_matter(self):
        repo, session = _repo_with_mock_session()
        assert repo.search_text("   ", filters=FILTERS) == []
        session.scalars.assert_not_called()


class TestIdenticalConstraintsAcrossBothPaths:
    """The stage 6 acceptance criterion, verified directly: both methods
    produce a WHERE clause containing the exact same filter fragments for
    the same SearchFilters object, because both call the same
    build_document_filters()."""

    @pytest.mark.parametrize("fragment", [
        "documents.document_type IN ('webpage')",
        "documents.language IN ('pl')",
        "EXISTS (SELECT",
        "document_time_periods.document_id = documents.id",
    ])
    def test_same_filter_fragment_in_both_statements(self, fragment):
        similar_repo, similar_session = _repo_with_mock_session()
        similar_repo.get_similar([0.1], model="m", filters=FILTERS)
        similar_sql = _compiled_sql(similar_session)

        text_repo, text_session = _repo_with_mock_session()
        text_repo.search_text("wojna", filters=FILTERS)
        text_sql = _compiled_sql(text_session)

        assert fragment in similar_sql
        assert fragment in text_sql
