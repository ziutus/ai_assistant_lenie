"""Unit tests for WebsitesDBPostgreSQL.get_list() query construction.

Tests verify that SQL WHERE clauses use correct column names and parameterized queries.
Uses sys.modules mocking to avoid psycopg2 dependency.
"""

import sys
from unittest.mock import MagicMock

import pytest

# Mock psycopg2 before importing the module under test
_mock_psycopg2 = MagicMock()
sys.modules["psycopg2"] = _mock_psycopg2


@pytest.fixture(autouse=True)
def _reset_psycopg2_mock():
    """Reset mock state before each test."""
    _mock_psycopg2.reset_mock()
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = []
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    _mock_psycopg2.connect.return_value = mock_conn
    yield mock_conn, mock_cursor


@pytest.fixture
def db_instance(_reset_psycopg2_mock):
    """Create a WebsitesDBPostgreSQL instance with mocked connection."""
    mock_conn, mock_cursor = _reset_psycopg2_mock

    from library.stalker_web_documents_db_postgresql import WebsitesDBPostgreSQL

    instance = WebsitesDBPostgreSQL()
    instance._mock_cursor = mock_cursor
    return instance


class TestGetListProjectFilter:
    """Tests for the project filter in get_list()."""

    def test_project_filter_uses_project_column(self, db_instance):
        """Verify that project filter generates 'project = %s', not 'document_state = %s'."""
        db_instance.get_list(project="my-project")

        call_args = db_instance._mock_cursor.execute.call_args
        query = call_args[0][0]
        params = call_args[0][1]

        assert "project = %s" in query, f"Expected 'project = %s' in query, got: {query}"
        assert "my-project" in params, f"Expected 'my-project' in params, got: {params}"

    def test_project_filter_does_not_use_document_state_for_project(self, db_instance):
        """Ensure project filter doesn't accidentally filter by document_state."""
        db_instance.get_list(project="test-project", document_state="ALL")

        call_args = db_instance._mock_cursor.execute.call_args
        query = call_args[0][0]

        # When document_state is ALL, there should be no "document_state = %s" in query
        assert query.count("document_state = %s") == 0, (
            f"project filter should not generate 'document_state = %s' clause, got: {query}"
        )
        assert "project = %s" in query


class TestGetListParameterization:
    """Tests verifying all filters use parameterized queries."""

    def test_document_type_parameterized(self, db_instance):
        """Verify document_type filter uses %s placeholder."""
        db_instance.get_list(document_type="webpage")

        call_args = db_instance._mock_cursor.execute.call_args
        query = call_args[0][0]
        params = call_args[0][1]

        assert "document_type = %s" in query
        assert "webpage" in params

    def test_document_state_parameterized(self, db_instance):
        """Verify document_state filter uses %s placeholder."""
        db_instance.get_list(document_state="URL_ADDED")

        call_args = db_instance._mock_cursor.execute.call_args
        query = call_args[0][0]
        params = call_args[0][1]

        assert "document_state = %s" in query
        assert "URL_ADDED" in params

    def test_search_in_documents_parameterized(self, db_instance):
        """Verify search_in_documents uses LIKE %s (not f-string)."""
        db_instance.get_list(search_in_documents="https://example.com")

        call_args = db_instance._mock_cursor.execute.call_args
        query = call_args[0][0]
        params = call_args[0][1]

        assert "LIKE %s" in query
        assert "%https://example.com%" in params

    def test_search_includes_url_field(self, db_instance):
        """Verify search_in_documents searches in url column."""
        db_instance.get_list(search_in_documents="test")

        call_args = db_instance._mock_cursor.execute.call_args
        query = call_args[0][0]

        assert "url LIKE %s" in query

    def test_combined_filters_all_parameterized(self, db_instance):
        """Verify combining multiple filters all use parameterized queries."""
        db_instance.get_list(
            document_type="webpage",
            document_state="URL_ADDED",
            project="my-project",
            search_in_documents="test",
        )

        call_args = db_instance._mock_cursor.execute.call_args
        query, params = call_args[0][0], call_args[0][1]

        assert "document_type = %s" in query
        assert "document_state = %s" in query
        assert "project = %s" in query
        assert "LIKE %s" in query
        # No string interpolation of values in the query itself
        assert "webpage" not in query
        assert "URL_ADDED" not in query
        assert "my-project" not in query
        assert len(params) > 0

    def test_no_filters_no_where_clause(self, db_instance):
        """Verify no WHERE clause when all filters are default."""
        db_instance.get_list()

        call_args = db_instance._mock_cursor.execute.call_args
        query = call_args[0][0]

        assert "WHERE" not in query
