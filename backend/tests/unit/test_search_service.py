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
# Tests: search() — the only hybrid entry point (stage 12 removed the legacy
# search_similar()/POST /website_similar path; behaviours worth keeping were
# ported here).
# ---------------------------------------------------------------------------


class TestHybridSearch:
    @patch("library.search_service.embedding.get_embedding")
    @patch("library.search_service.load_config")
    def test_happy_path_with_results(self, mock_config, mock_get_embedding):
        """search() returns merged results from the semantic path."""
        cfg = MagicMock()
        cfg.require.return_value = "text-embedding-ada-002"
        mock_config.return_value = cfg

        mock_get_embedding.return_value = _make_embedding_result()

        session = _make_session()
        service = SearchService(session)

        expected_results = [{"document_id": 1, "similarity": 0.9}]
        with patch.object(service.repo, "search_text", return_value=[]),              patch.object(service.repo, "get_similar", return_value=expected_results) as mock_similar:
            result = service.search("test query", SearchFilters(), limit=3)

        assert result[0]["document_id"] == 1
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
    def test_embedding_failure_without_lexical_raises(self, mock_config, mock_get_embedding):
        """search() raises RuntimeError when embedding fails and there are no lexical hits."""
        cfg = MagicMock()
        cfg.require.return_value = "text-embedding-ada-002"
        mock_config.return_value = cfg

        mock_get_embedding.return_value = _make_embedding_result(status="error", embedding=[])

        session = _make_session()
        service = SearchService(session)

        with patch.object(service.repo, "search_text", return_value=[]):
            with pytest.raises(RuntimeError, match="Embedding generation failed"):
                service.search("test query", SearchFilters(), limit=3)

    @patch("library.search_service.embedding.get_embedding")
    @patch("library.search_service.load_config")
    def test_empty_embedding_without_lexical_raises(self, mock_config, mock_get_embedding):
        cfg = MagicMock()
        cfg.require.return_value = "text-embedding-ada-002"
        mock_config.return_value = cfg

        mock_get_embedding.return_value = _make_embedding_result(status="success", embedding=[])

        session = _make_session()
        service = SearchService(session)

        with patch.object(service.repo, "search_text", return_value=[]):
            with pytest.raises(RuntimeError, match="Embedding generation failed"):
                service.search("test query", SearchFilters(), limit=3)

    @patch("library.search_service.embedding.get_embedding")
    @patch("library.search_service.load_config")
    def test_custom_limit_scales_candidate_pool(self, mock_config, mock_get_embedding):
        cfg = MagicMock()
        cfg.require.return_value = "text-embedding-ada-002"
        mock_config.return_value = cfg

        mock_get_embedding.return_value = _make_embedding_result()

        session = _make_session()
        service = SearchService(session)

        with patch.object(service.repo, "search_text", return_value=[]),              patch.object(service.repo, "get_similar", return_value=[]) as mock_similar:
            service.search("test query", SearchFilters(), limit=10)

        mock_similar.assert_called_once_with(
            [0.1, 0.2, 0.3],
            "text-embedding-ada-002",
            limit=50,
            filters=SearchFilters(),
        )

    @patch("library.search_service.embedding.get_embedding")
    @patch("library.search_service.load_config")
    def test_filters_forwarded_to_both_paths(self, mock_config, mock_get_embedding):
        """The SAME SearchFilters reaches lexical and vector search (stage 6 criterion)."""
        cfg = MagicMock()
        cfg.require.return_value = "test-model"
        mock_config.return_value = cfg
        mock_get_embedding.return_value = _make_embedding_result()
        service = SearchService(_make_session())
        filters = SearchFilters(collection_name="my-project",
                                subject_period_start_year=1939,
                                subject_period_end_year=1945)
        with patch.object(service.repo, "search_text", return_value=[]) as mock_text,              patch.object(service.repo, "get_similar", return_value=[]) as mock_similar:
            service.search("zapytanie", filters, limit=10)

        assert mock_text.call_args.kwargs["filters"] == filters
        assert mock_similar.call_args.kwargs["filters"] == filters

    @patch("library.search_service.embedding.get_embedding")
    @patch("library.search_service.load_config")
    def test_empty_results(self, mock_config, mock_get_embedding):
        cfg = MagicMock()
        cfg.require.return_value = "text-embedding-ada-002"
        mock_config.return_value = cfg

        mock_get_embedding.return_value = _make_embedding_result()

        session = _make_session()
        service = SearchService(session)

        with patch.object(service.repo, "search_text", return_value=[]),              patch.object(service.repo, "get_similar", return_value=[]):
            result = service.search("obscure query", SearchFilters(), limit=3)

        assert result == []

    @patch("library.search_service.embedding.get_embedding")
    @patch("library.search_service.load_config")
    def test_exact_title_is_returned_without_document_embedding(self, mock_config, mock_get_embedding):
        """Embedding failure degrades to lexical-only results instead of a 500."""
        cfg = MagicMock()
        cfg.require.return_value = "test-model"
        mock_config.return_value = cfg
        mock_get_embedding.return_value = _make_embedding_result(status="error", embedding=[])
        service = SearchService(_make_session())
        lexical = [{
            "document_id": 9242,
            "title": "Wojna w Ukrainie. Rosyjscy szpiedzy przenieśli działalność do Japonii",
            "text": "Artykuł o rosyjskich agentach w Japonii.",
            "similarity": 0.0,
        }]
        with patch.object(service.repo, "search_text", return_value=lexical),              patch.object(service.repo, "get_similar", return_value=[]) as mock_similar:
            result = service.search("Rosyjscy szpiedzy w Japonii", SearchFilters(), limit=10)

        assert result[0]["document_id"] == 9242
        assert result[0]["search_match"] == "text"
        assert result[0]["similarity"] > 0.5
        mock_similar.assert_not_called()


class TestSearchByFilters:
    """Stage 6 session B: filter-only listing, no embedding generated."""

    def test_delegates_to_repo_list_by_filters(self):
        service = SearchService(_make_session())
        filters = SearchFilters(document_types=("webpage",))
        with patch.object(service.repo, "list_by_filters", return_value=[{"document_id": 1}]) as mock_list:
            result = service.search_by_filters(filters, limit=15, offset=5, sort=SearchSort.PUBLISHED_DESC)

        assert result == [{"document_id": 1}]
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
        with patch.object(service.repo, "list_by_filters", return_value=[{"document_id": 1}, {"document_id": 2}]):
            result = service.search_by_filters(SearchFilters())

        assert len(result) == 2


class TestStage8Search:
    def test_missing_query_delegates_without_embedding(self):
        service = SearchService(_make_session())
        filters = SearchFilters(languages=("pl",))
        with patch.object(service, "search_by_filters", return_value=[]) as filter_search, \
             patch("library.search_service.embedding.get_embedding") as embedding:
            service.search(None, filters, limit=4, offset=2, sort=SearchSort.PUBLISHED_ASC)
        filter_search.assert_called_once_with(
            filters, limit=4, offset=2, sort=SearchSort.PUBLISHED_ASC,
        )
        embedding.assert_not_called()

    @patch("library.search_service.embedding.get_embedding")
    @patch("library.search_service.load_config")
    def test_query_forwards_all_filters_and_slices_offset(self, config, get_embedding):
        config.return_value.require.return_value = "model"
        get_embedding.return_value = _make_embedding_result()
        service = SearchService(_make_session())
        filters = SearchFilters(author_name="Jan")
        merged = [{"document_id": n} for n in range(6)]
        with patch.object(service.repo, "search_text", return_value=[]) as lexical, \
             patch.object(service.repo, "get_similar", return_value=[]) as semantic, \
             patch.object(service, "_merge_results", return_value=merged) as merge:
            result = service.search("temat", filters, limit=2, offset=3)
        assert result == merged[3:5]
        assert lexical.call_args.kwargs["filters"] is filters
        assert semantic.call_args.kwargs["filters"] is filters
        assert merge.call_args.args[-1] == 5

    @patch("library.search_service.embedding.get_embedding")
    @patch("library.search_service.load_config")
    def test_embedding_failure_uses_lexical_results(self, config, get_embedding):
        config.return_value.require.return_value = "model"
        get_embedding.return_value = _make_embedding_result(status="error")
        service = SearchService(_make_session())
        with patch.object(service.repo, "search_text", return_value=[{"document_id": 1}]), \
             patch.object(service, "_merge_results", return_value=[{"document_id": 1}]):
            assert service.search("temat", SearchFilters()) == [{"document_id": 1}]

    @patch("library.search_service.embedding.get_embedding")
    @patch("library.search_service.load_config")
    def test_explicit_published_sort_is_applied_after_ranking(self, config, get_embedding):
        config.return_value.require.return_value = "model"
        get_embedding.return_value = _make_embedding_result()
        service = SearchService(_make_session())
        merged = [
            {"document_id": 1, "published_on": None},
            {"document_id": 2, "published_on": "2020-01-01"},
            {"document_id": 3, "published_on": "2022-01-01"},
        ]
        with patch.object(service.repo, "search_text", return_value=[]), \
             patch.object(service.repo, "get_similar", return_value=[]), \
             patch.object(service, "_merge_results", return_value=merged):
            result = service.search(
                "temat", SearchFilters(), sort=SearchSort.PUBLISHED_DESC,
            )
        assert [item["document_id"] for item in result] == [3, 2, 1]
