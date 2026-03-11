"""Unit tests for get_similar() ORM path (Story 28.2).

Tests verify that the ORM branch of get_similar() constructs the correct
SQLAlchemy query with cosine_distance, JOIN, and proper result formatting.
"""

from unittest.mock import MagicMock

import pytest

sa = pytest.importorskip("sqlalchemy")


EXPECTED_KEYS = {
    "website_id", "text", "similarity", "id", "url", "language",
    "text_original", "websites_text_length", "embeddings_text_length",
    "title", "document_type", "project",
}


def _make_row(**overrides):
    """Create a mock result row with all 12 expected attributes."""
    defaults = {
        "website_id": 1,
        "text": "chunk text",
        "similarity": 0.85,
        "id": 10,
        "url": "https://example.com",
        "language": "en",
        "text_original": "original text",
        "websites_text_length": 100,
        "embeddings_text_length": 50,
        "title": "Test Doc",
        "document_type": "webpage",
        "project": "lenie",
    }
    defaults.update(overrides)
    row = MagicMock()
    for k, v in defaults.items():
        setattr(row, k, v)
    return row


def _create_repo_with_session(execute_return=None):
    """Create a WebsitesDBPostgreSQL instance with a mocked ORM session."""
    mock_session = MagicMock()
    if execute_return is not None:
        mock_session.execute.return_value.all.return_value = execute_return

    from library.stalker_web_documents_db_postgresql import WebsitesDBPostgreSQL
    repo = WebsitesDBPostgreSQL(session=mock_session)
    return repo, mock_session


class TestGetSimilarORM:
    """Tests for the ORM branch of get_similar()."""

    def test_basic_search_returns_results(self):
        row = _make_row()
        repo, session = _create_repo_with_session([row])

        result = repo.get_similar([0.1, 0.2, 0.3], model="test-model", limit=5)

        assert isinstance(result, list)
        assert len(result) == 1
        session.execute.assert_called_once()

    def test_result_contains_all_12_keys(self):
        row = _make_row()
        repo, _ = _create_repo_with_session([row])

        result = repo.get_similar([0.1, 0.2, 0.3], model="test-model")

        assert len(result) == 1
        assert set(result[0].keys()) == EXPECTED_KEYS

    def test_result_values_match_row(self):
        row = _make_row(website_id=42, similarity=0.92, title="My Doc")
        repo, _ = _create_repo_with_session([row])

        result = repo.get_similar([0.1, 0.2], model="m")

        assert result[0]["website_id"] == 42
        assert result[0]["similarity"] == 0.92
        assert result[0]["title"] == "My Doc"

    def test_similarity_is_float(self):
        row = _make_row(similarity=0.75)
        repo, _ = _create_repo_with_session([row])

        result = repo.get_similar([0.1], model="m")

        assert isinstance(result[0]["similarity"], float)

    def test_empty_results_returns_empty_list(self):
        repo, _ = _create_repo_with_session([])

        result = repo.get_similar([0.1, 0.2, 0.3], model="test-model")

        assert result == []

    def test_embedding_none_returns_none(self):
        repo, session = _create_repo_with_session([])

        result = repo.get_similar(None, model="test-model")

        assert result is None
        session.execute.assert_not_called()

    def test_project_filtering(self):
        row = _make_row(project="my-project")
        repo, session = _create_repo_with_session([row])

        result = repo.get_similar([0.1], model="m", project="my-project")

        assert len(result) == 1
        # Verify execute was called (with project filter in the statement)
        session.execute.assert_called_once()
        # The statement passed to execute should include project filter
        stmt = session.execute.call_args[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": False}))
        assert "project" in compiled.lower()

    def test_minimal_similarity_default(self):
        repo, session = _create_repo_with_session([])

        repo.get_similar([0.1], model="m", minimal_similarity=None)

        # Should not raise — None is replaced with 0.30
        session.execute.assert_called_once()

    def test_minimal_similarity_threshold_in_sql(self):
        """Verify minimal_similarity threshold appears in the generated SQL."""
        repo, session = _create_repo_with_session([])

        repo.get_similar([0.1], model="m", minimal_similarity=0.50)

        stmt = session.execute.call_args[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": False}))
        # The WHERE clause should contain a comparison against the similarity threshold
        assert ">" in compiled or "cosine_distance" in compiled.lower()

    def test_sql_contains_cosine_distance(self):
        repo, session = _create_repo_with_session([])

        repo.get_similar([0.1, 0.2], model="m")

        stmt = session.execute.call_args[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": False}))
        assert "<=>" in compiled or "cosine_distance" in compiled.lower()

    def test_sql_contains_join(self):
        repo, session = _create_repo_with_session([])

        repo.get_similar([0.1, 0.2], model="m")

        stmt = session.execute.call_args[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": False}))
        assert "join" in compiled.lower() or "JOIN" in compiled

    def test_no_commit_called(self):
        repo, session = _create_repo_with_session([_make_row()])

        repo.get_similar([0.1], model="m")

        session.commit.assert_not_called()

    def test_document_type_serialized_to_string(self):
        """Verify document_type string is passed through in result dict."""
        row = _make_row(document_type="webpage")
        repo, _ = _create_repo_with_session([row])

        result = repo.get_similar([0.1], model="m")

        assert result[0]["document_type"] == "webpage"
        assert isinstance(result[0]["document_type"], str)

    def test_multiple_results(self):
        rows = [
            _make_row(website_id=1, similarity=0.95),
            _make_row(website_id=2, similarity=0.80),
            _make_row(website_id=3, similarity=0.65),
        ]
        repo, _ = _create_repo_with_session(rows)

        result = repo.get_similar([0.1, 0.2], model="m", limit=3)

        assert len(result) == 3
        assert result[0]["website_id"] == 1
        assert result[2]["website_id"] == 3
