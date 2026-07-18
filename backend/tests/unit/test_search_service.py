"""Unit tests for SearchService (Story 32.2).

All tests use mocked sessions - no database required.
"""

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("sqlalchemy")

from library.search_service import SearchService
from library.models.embedding_result import EmbeddingResult
from library.search.types import SearchFilters, SearchSort


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
            filters=SearchFilters(),
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
            filters=SearchFilters(),
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
            filters=SearchFilters(collection_name="my-project"),
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
    """Stage 6: the period window is now a SearchFilters passed to the repo
    (applied in SQL before LIMIT), not a Python-side post-filter -- see
    tests/unit/test_repository_sql_filters.py for the SQL-level proof."""

    @patch("library.search_service.embedding.get_embedding")
    @patch("library.search_service.load_config")
    def test_period_window_is_forwarded_as_filters(self, mock_config, mock_get_embedding):
        cfg = MagicMock()
        cfg.require.return_value = "test-model"
        mock_config.return_value = cfg
        mock_get_embedding.return_value = _make_embedding_result()
        service = SearchService(_make_session())
        with patch.object(service.repo, "search_text", return_value=[]) as mock_text, \
             patch.object(service.repo, "get_similar", return_value=[]) as mock_similar:
            service.search_similar("zapytanie", limit=10, period_from=1939, period_to=1945)

        expected_filters = SearchFilters(subject_period_start_year=1939, subject_period_end_year=1945)
        assert mock_text.call_args.kwargs["filters"] == expected_filters
        assert mock_similar.call_args.kwargs["filters"] == expected_filters

    @patch("library.search_service.embedding.get_embedding")
    @patch("library.search_service.load_config")
    def test_no_period_window_yields_empty_filters(self, mock_config, mock_get_embedding):
        cfg = MagicMock()
        cfg.require.return_value = "test-model"
        mock_config.return_value = cfg
        mock_get_embedding.return_value = _make_embedding_result()
        service = SearchService(_make_session())
        with patch.object(service.repo, "search_text", return_value=[]), \
             patch.object(service.repo, "get_similar", return_value=[]) as mock_similar:
            service.search_similar("zapytanie", limit=10)

        assert mock_similar.call_args.kwargs["filters"] == SearchFilters()

    @patch("library.search_service.embedding.get_embedding")
    @patch("library.search_service.load_config")
    def test_reversed_period_is_swapped_not_rejected(self, mock_config, mock_get_embedding):
        cfg = MagicMock()
        cfg.require.return_value = "test-model"
        mock_config.return_value = cfg
        mock_get_embedding.return_value = _make_embedding_result()
        service = SearchService(_make_session())
        with patch.object(service.repo, "search_text", return_value=[]), \
             patch.object(service.repo, "get_similar", return_value=[]) as mock_similar:
            service.search_similar("zapytanie", period_from=1945, period_to=1939)

        filters = mock_similar.call_args.kwargs["filters"]
        assert filters.subject_period_start_year == 1939
        assert filters.subject_period_end_year == 1945

    @patch("library.search_service.embedding.get_embedding")
    @patch("library.search_service.load_config")
    def test_out_of_domain_year_degrades_to_no_filter_instead_of_raising(self, mock_config, mock_get_embedding):
        cfg = MagicMock()
        cfg.require.return_value = "test-model"
        mock_config.return_value = cfg
        mock_get_embedding.return_value = _make_embedding_result()
        service = SearchService(_make_session())
        with patch.object(service.repo, "search_text", return_value=[]), \
             patch.object(service.repo, "get_similar", return_value=[]) as mock_similar:
            # 999_999 is outside [MIN_SUBJECT_YEAR, MAX_SUBJECT_YEAR] -- must
            # not raise SearchQueryValidationError out of a public API that
            # accepts untrusted HTTP params.
            service.search_similar("zapytanie", period_from=999_999)

        assert mock_similar.call_args.kwargs["filters"] == SearchFilters()

    @patch("library.search_service.embedding.get_embedding")
    @patch("library.search_service.load_config")
    def test_blank_project_treated_as_no_collection_filter(self, mock_config, mock_get_embedding):
        cfg = MagicMock()
        cfg.require.return_value = "test-model"
        mock_config.return_value = cfg
        mock_get_embedding.return_value = _make_embedding_result()
        service = SearchService(_make_session())
        with patch.object(service.repo, "search_text", return_value=[]), \
             patch.object(service.repo, "get_similar", return_value=[]) as mock_similar:
            # An empty string used to be a falsy no-op (`if project:`);
            # SearchFilters(collection_name="") would raise -- must still
            # degrade to "no collection filter", not crash.
            service.search_similar("zapytanie", project="")

        assert mock_similar.call_args.kwargs["filters"] == SearchFilters()


class TestSearchByFilters:
    """Stage 6 session B: filter-only listing, no embedding generated."""

    def test_delegates_to_repo_list_by_filters(self):
        service = SearchService(_make_session())
        filters = SearchFilters(document_types=("webpage",))
        with patch.object(service.repo, "list_by_filters", return_value=[{"website_id": 1}]) as mock_list:
            result = service.search_by_filters(filters, limit=15, offset=5, sort=SearchSort.PUBLISHED_DESC)

        assert result == [{"website_id": 1}]
        mock_list.assert_called_once_with(filters, limit=15, offset=5, sort=SearchSort.PUBLISHED_DESC)

    def test_defaults(self):
        service = SearchService(_make_session())
        filters = SearchFilters()
        with patch.object(service.repo, "list_by_filters", return_value=[]) as mock_list:
            service.search_by_filters(filters)

        mock_list.assert_called_once_with(filters, limit=20, offset=0, sort=SearchSort.RELEVANCE)

    @patch("library.search_service.embedding.get_embedding")
    def test_never_generates_an_embedding(self, mock_get_embedding):
        service = SearchService(_make_session())
        with patch.object(service.repo, "list_by_filters", return_value=[]):
            service.search_by_filters(SearchFilters(document_types=("webpage",)))

        mock_get_embedding.assert_not_called()

    def test_empty_filters_allowed_lists_everything(self):
        service = SearchService(_make_session())
        with patch.object(service.repo, "list_by_filters", return_value=[{"website_id": 1}, {"website_id": 2}]):
            result = service.search_by_filters(SearchFilters())

        assert len(result) == 2
