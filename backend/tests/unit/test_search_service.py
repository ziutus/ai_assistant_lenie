"""Unit tests for SearchService (Story 32.2).

All tests use mocked sessions - no database required.
"""

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("sqlalchemy")

from library.search_service import SearchService
from library.models.embedding_result import EmbeddingResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session():
    """Return a mock SQLAlchemy session."""
    return MagicMock()


def _make_embedding_result(status="success", embedding=None, text="test"):
    """Return an EmbeddingResult with safe defaults."""
    if embedding is None:
        embedding = [0.1, 0.2, 0.3]
    return EmbeddingResult(text=text, embedding=embedding, status=status)


# ---------------------------------------------------------------------------
# Tests: __init__
# ---------------------------------------------------------------------------


class TestSearchServiceInit:
    def test_stores_session(self):
        session = _make_session()
        service = SearchService(session)
        assert service.session is session

    def test_creates_repo(self):
        session = _make_session()
        service = SearchService(session)
        assert service.repo is not None


# ---------------------------------------------------------------------------
# Tests: get_embedding
# ---------------------------------------------------------------------------


class TestGetEmbedding:
    @patch("library.search_service.embedding.get_embedding")
    @patch("library.search_service.load_config")
    def test_happy_path(self, mock_config, mock_get_embedding):
        """get_embedding returns EmbeddingResult from embedding module."""
        cfg = MagicMock()
        cfg.require.return_value = "text-embedding-ada-002"
        mock_config.return_value = cfg

        expected = _make_embedding_result()
        mock_get_embedding.return_value = expected

        session = _make_session()
        service = SearchService(session)
        result = service.get_embedding("hello world")

        assert result is expected
        mock_get_embedding.assert_called_once_with(model="text-embedding-ada-002", text="hello world")

    @patch("library.search_service.embedding.get_embedding")
    @patch("library.search_service.load_config")
    def test_model_from_config(self, mock_config, mock_get_embedding):
        """get_embedding reads EMBEDDING_MODEL from config_loader."""
        cfg = MagicMock()
        cfg.require.return_value = "amazon.titan-embed-text-v2:0"
        mock_config.return_value = cfg

        mock_get_embedding.return_value = _make_embedding_result()

        session = _make_session()
        service = SearchService(session)
        service.get_embedding("test text")

        cfg.require.assert_called_once_with("EMBEDDING_MODEL")
        mock_get_embedding.assert_called_once_with(model="amazon.titan-embed-text-v2:0", text="test text")


# ---------------------------------------------------------------------------
# Tests: search_similar
# ---------------------------------------------------------------------------


class TestSearchSimilar:
    @patch("library.search_service.embedding.get_embedding")
    @patch("library.search_service.load_config")
    def test_happy_path_with_results(self, mock_config, mock_get_embedding):
        """search_similar returns list of similar documents."""
        cfg = MagicMock()
        cfg.require.return_value = "text-embedding-ada-002"
        mock_config.return_value = cfg

        mock_get_embedding.return_value = _make_embedding_result()

        session = _make_session()
        service = SearchService(session)

        expected_results = [{"website_id": 1, "similarity": 0.9}]
        with patch.object(service.repo, "search_text", return_value=[]), \
             patch.object(service.repo, "get_similar", return_value=expected_results) as mock_similar:
            result = service.search_similar("test query")

        assert result[0]["website_id"] == 1
        assert result[0]["similarity"] == 0.9
        assert result[0]["search_match"] == "semantic"
        mock_similar.assert_called_once_with(
            [0.1, 0.2, 0.3],
            "text-embedding-ada-002",
            limit=20,
            project=None,
        )

    @patch("library.search_service.embedding.get_embedding")
    @patch("library.search_service.load_config")
    def test_embedding_failure_raises(self, mock_config, mock_get_embedding):
        """search_similar raises RuntimeError when embedding generation fails."""
        cfg = MagicMock()
        cfg.require.return_value = "text-embedding-ada-002"
        mock_config.return_value = cfg

        mock_get_embedding.return_value = _make_embedding_result(status="error", embedding=[])

        session = _make_session()
        service = SearchService(session)

        with pytest.raises(RuntimeError, match="Embedding generation failed"):
            service.search_similar("test query")

    @patch("library.search_service.embedding.get_embedding")
    @patch("library.search_service.load_config")
    def test_empty_embedding_raises(self, mock_config, mock_get_embedding):
        """search_similar raises RuntimeError when embedding vector is empty."""
        cfg = MagicMock()
        cfg.require.return_value = "text-embedding-ada-002"
        mock_config.return_value = cfg

        mock_get_embedding.return_value = _make_embedding_result(status="success", embedding=[])

        session = _make_session()
        service = SearchService(session)

        with pytest.raises(RuntimeError, match="Embedding generation failed"):
            service.search_similar("test query")

    @patch("library.search_service.embedding.get_embedding")
    @patch("library.search_service.load_config")
    def test_custom_limit(self, mock_config, mock_get_embedding):
        """search_similar passes custom limit to repo.get_similar()."""
        cfg = MagicMock()
        cfg.require.return_value = "text-embedding-ada-002"
        mock_config.return_value = cfg

        mock_get_embedding.return_value = _make_embedding_result()

        session = _make_session()
        service = SearchService(session)

        with patch.object(service.repo, "get_similar", return_value=[]) as mock_similar:
            service.search_similar("test query", limit=10)

        mock_similar.assert_called_once_with(
            [0.1, 0.2, 0.3],
            "text-embedding-ada-002",
            limit=50,
            project=None,
        )

    @patch("library.search_service.embedding.get_embedding")
    @patch("library.search_service.load_config")
    def test_custom_project(self, mock_config, mock_get_embedding):
        """search_similar passes project filter to repo.get_similar()."""
        cfg = MagicMock()
        cfg.require.return_value = "text-embedding-ada-002"
        mock_config.return_value = cfg

        mock_get_embedding.return_value = _make_embedding_result()

        session = _make_session()
        service = SearchService(session)

        with patch.object(service.repo, "get_similar", return_value=[]) as mock_similar:
            service.search_similar("test query", project="my-project")

        mock_similar.assert_called_once_with(
            [0.1, 0.2, 0.3],
            "text-embedding-ada-002",
            limit=20,
            project="my-project",
        )

    @patch("library.search_service.embedding.get_embedding")
    @patch("library.search_service.load_config")
    def test_empty_results(self, mock_config, mock_get_embedding):
        """search_similar returns empty list when no similar documents found."""
        cfg = MagicMock()
        cfg.require.return_value = "text-embedding-ada-002"
        mock_config.return_value = cfg

        mock_get_embedding.return_value = _make_embedding_result()

        session = _make_session()
        service = SearchService(session)

        with patch.object(service.repo, "get_similar", return_value=[]):
            result = service.search_similar("obscure query")

        assert result == []

    @patch("library.search_service.embedding.get_embedding")
    @patch("library.search_service.load_config")
    def test_exact_title_is_returned_without_document_embedding(self, mock_config, mock_get_embedding):
        cfg = MagicMock()
        cfg.require.return_value = "test-model"
        mock_config.return_value = cfg
        mock_get_embedding.return_value = _make_embedding_result(status="error", embedding=[])
        service = SearchService(_make_session())
        lexical = [{
            "website_id": 9242,
            "title": "Wojna w Ukrainie. Rosyjscy szpiedzy przenieśli działalność do Japonii",
            "text": "Artykuł o rosyjskich agentach w Japonii.",
            "similarity": 0.0,
        }]
        with patch.object(service.repo, "search_text", return_value=lexical), \
             patch.object(service.repo, "get_similar", return_value=[]) as mock_similar:
            result = service.search_similar("Rosyjscy szpiedzy w Japonii", limit=10)

        assert result[0]["website_id"] == 9242
        assert result[0]["search_match"] == "text"
        assert result[0]["similarity"] > 0.5
        mock_similar.assert_not_called()


class TestPeriodFilter:
    @patch("library.search_service.embedding.get_embedding")
    @patch("library.search_service.load_config")
    def test_period_window_drops_documents_outside_it(self, mock_config, mock_get_embedding):
        cfg = MagicMock()
        cfg.require.return_value = "test-model"
        mock_config.return_value = cfg
        mock_get_embedding.return_value = _make_embedding_result()
        service = SearchService(_make_session())
        semantic = [
            {"website_id": 1, "similarity": 0.9},
            {"website_id": 2, "similarity": 0.8},
        ]
        with patch.object(service.repo, "search_text", return_value=[]), \
             patch.object(service.repo, "get_similar", return_value=semantic), \
             patch.object(service, "_documents_in_period", return_value={1}) as mock_period:
            result = service.search_similar("zapytanie", limit=10, period_from=1939, period_to=1945)

        assert [row["website_id"] for row in result] == [1]
        mock_period.assert_called_once_with(1939, 1945)

    @patch("library.search_service.embedding.get_embedding")
    @patch("library.search_service.load_config")
    def test_no_period_window_skips_the_filter(self, mock_config, mock_get_embedding):
        cfg = MagicMock()
        cfg.require.return_value = "test-model"
        mock_config.return_value = cfg
        mock_get_embedding.return_value = _make_embedding_result()
        service = SearchService(_make_session())
        with patch.object(service.repo, "search_text", return_value=[]), \
             patch.object(service.repo, "get_similar", return_value=[{"website_id": 1, "similarity": 0.9}]), \
             patch.object(service, "_documents_in_period") as mock_period:
            result = service.search_similar("zapytanie", limit=10)

        assert [row["website_id"] for row in result] == [1]
        mock_period.assert_not_called()

    @pytest.mark.parametrize(
        ("period_from", "period_to", "expected_filters"),
        [(1939, 1945, 2), (1939, None, 1), (None, -500, 1)],
    )
    def test_documents_in_period_builds_one_filter_per_bound(self, period_from, period_to, expected_filters):
        session = _make_session()
        query = MagicMock()
        session.query.return_value = query
        query.filter.return_value = query
        query.distinct.return_value = [(5,), (7,)]
        service = SearchService(session)

        assert service._documents_in_period(period_from, period_to) == {5, 7}
        assert query.filter.call_count == expected_filters
