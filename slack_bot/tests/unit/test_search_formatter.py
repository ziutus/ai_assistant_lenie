"""Unit tests for src.search_formatter module."""

from unittest.mock import patch

from src.search_formatter import format_search_results, get_search_results_limit


# --- Test get_search_results_limit ---


class TestGetSearchResultsLimit:
    def test_default_value(self):
        with patch.dict("os.environ", {}, clear=True):
            assert get_search_results_limit() == 5

    def test_custom_value(self):
        with patch.dict("os.environ", {"SEARCH_RESULTS_LIMIT": "3"}):
            assert get_search_results_limit() == 3

    def test_invalid_value_returns_default(self):
        with patch.dict("os.environ", {"SEARCH_RESULTS_LIMIT": "abc"}):
            assert get_search_results_limit() == 5

    def test_empty_value_returns_default(self):
        with patch.dict("os.environ", {"SEARCH_RESULTS_LIMIT": ""}):
            assert get_search_results_limit() == 5


# --- Test format_search_results ---


class TestFormatSearchResults:
    def test_no_results(self):
        result = format_search_results("kubernetes", [])
        assert "No similar documents found for 'kubernetes'." == result

    def test_single_result(self):
        results = [
            {
                "website_id": 1,
                "title": "K8s Security Guide",
                "url": "https://example.com/k8s",
                "document_type": "webpage",
                "similarity": 0.87,
                "language": "en",
            }
        ]
        text = format_search_results("kubernetes security", results)
        assert 'Found 1 result for "kubernetes security"' in text
        assert "*K8s Security Guide*" in text
        assert "webpage" in text
        assert "87%" in text
        assert "https://example.com/k8s" in text

    def test_multiple_results(self):
        results = [
            {
                "title": "Article A",
                "url": "https://a.com",
                "document_type": "webpage",
                "similarity": 0.90,
            },
            {
                "title": "Article B",
                "url": "https://b.com",
                "document_type": "youtube",
                "similarity": 0.75,
            },
            {
                "title": "Article C",
                "url": "https://c.com",
                "document_type": "link",
                "similarity": 0.60,
            },
        ]
        text = format_search_results("test query", results)
        assert 'Found 3 results for "test query"' in text
        assert "1. *Article A*" in text
        assert "2. *Article B*" in text
        assert "3. *Article C*" in text
        assert "90%" in text
        assert "75%" in text
        assert "60%" in text

    def test_no_title_uses_url(self):
        results = [
            {
                "title": None,
                "url": "https://example.com/no-title",
                "document_type": "link",
                "similarity": 0.50,
            }
        ]
        text = format_search_results("query", results)
        assert "*https://example.com/no-title*" in text

    def test_empty_title_uses_url(self):
        results = [
            {
                "title": "",
                "url": "https://example.com/empty",
                "document_type": "webpage",
                "similarity": 0.40,
            }
        ]
        text = format_search_results("query", results)
        assert "*https://example.com/empty*" in text

    def test_respects_limit(self):
        results = [
            {"title": f"Doc {i}", "url": f"https://ex.com/{i}", "document_type": "webpage", "similarity": 0.9 - i * 0.1}
            for i in range(10)
        ]
        with patch.dict("os.environ", {"SEARCH_RESULTS_LIMIT": "3"}):
            text = format_search_results("query", results)
        assert "Found 3 results" in text
        assert "1. *Doc 0*" in text
        assert "3. *Doc 2*" in text
        assert "Doc 3" not in text

    def test_default_limit_five(self):
        results = [
            {"title": f"Doc {i}", "url": f"https://ex.com/{i}", "document_type": "webpage", "similarity": 0.9 - i * 0.05}
            for i in range(8)
        ]
        with patch.dict("os.environ", {}, clear=True):
            text = format_search_results("query", results)
        assert "Found 5 results" in text
        assert "5. *Doc 4*" in text
        assert "Doc 5" not in text

    def test_similarity_as_percentage(self):
        results = [
            {"title": "Doc", "url": "https://ex.com", "document_type": "webpage", "similarity": 0.123}
        ]
        text = format_search_results("query", results)
        assert "12%" in text

    def test_no_url_field(self):
        results = [
            {"title": "Doc", "document_type": "webpage", "similarity": 0.5}
        ]
        text = format_search_results("query", results)
        assert "*Doc*" in text
        # Should not crash without url
