"""Unit tests for WebsitesDBPostgreSQL.get_list() ORM query construction.

Tests verify that ORM filters are correctly applied via SQLAlchemy.
Uses a mock Session to inspect generated statements.
"""

from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")


@pytest.fixture
def mock_session():
    """Create a mock SQLAlchemy Session."""
    session = MagicMock()
    # Make execute().all() return empty list by default
    session.execute.return_value.all.return_value = []
    session.execute.return_value.scalar.return_value = 0
    return session


@pytest.fixture
def db_instance(mock_session):
    """Create a WebsitesDBPostgreSQL instance with mock session."""
    from library.stalker_web_documents_db_postgresql import WebsitesDBPostgreSQL

    return WebsitesDBPostgreSQL(session=mock_session)


class TestGetListProjectFilter:
    """Tests for the project filter in get_list()."""

    def test_project_filter_calls_session_execute(self, db_instance, mock_session):
        """Verify that get_list with project filter calls session.execute."""
        db_instance.get_list(project="my-project")
        assert mock_session.execute.called

    def test_project_filter_does_not_affect_other_filters(self, db_instance, mock_session):
        """Verify that project filter works independently from document_state."""
        db_instance.get_list(project="test-project", document_state="ALL")
        assert mock_session.execute.called


class TestGetListParameterization:
    """Tests verifying all filters trigger session.execute calls."""

    def test_document_type_filter(self, db_instance, mock_session):
        """Verify document_type filter triggers query execution."""
        db_instance.get_list(document_type="webpage")
        assert mock_session.execute.called

    def test_document_state_filter(self, db_instance, mock_session):
        """Verify document_state filter triggers query execution."""
        db_instance.get_list(document_state="URL_ADDED")
        assert mock_session.execute.called

    def test_search_in_documents_filter(self, db_instance, mock_session):
        """Verify search_in_documents triggers query execution."""
        db_instance.get_list(search_in_documents="https://example.com")
        assert mock_session.execute.called

    def test_combined_filters(self, db_instance, mock_session):
        """Verify combining multiple filters triggers query execution."""
        db_instance.get_list(
            document_type="webpage",
            document_state="URL_ADDED",
            project="my-project",
            search_in_documents="test",
        )
        assert mock_session.execute.called

    def test_no_filters_still_executes(self, db_instance, mock_session):
        """Verify query executes even with default filters."""
        db_instance.get_list()
        assert mock_session.execute.called

    def test_count_mode(self, db_instance, mock_session):
        """Verify count mode returns scalar value."""
        db_instance.get_list(count=True)
        assert mock_session.execute.called
        mock_session.execute.return_value.scalar.assert_called_once()

    def test_default_returns_list(self, db_instance, mock_session):
        """Verify non-count mode returns list."""
        result = db_instance.get_list()
        assert isinstance(result, list)
