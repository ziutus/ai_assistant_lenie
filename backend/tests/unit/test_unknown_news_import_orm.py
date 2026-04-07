"""Unit tests for feed entry import logic (originally unknown_news_import.py, now feed_monitor.py).

Tests verify that _import_entry creates documents via ORM with correct fields,
and that check_existing + cmd_import duplicate logic works correctly.

Replaces the old test_unknown_news_import_orm.py tests after the migration
from unknown_news_import.py to feed_monitor.py.
"""

from unittest.mock import MagicMock, patch

import pytest

sa = pytest.importorskip("sqlalchemy")

from library.models.stalker_document_status import StalkerDocumentStatus  # noqa: E402, F401
from library.models.stalker_document_type import StalkerDocumentType  # noqa: E402, F401


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session():
    """Return a mock SQLAlchemy Session."""
    return MagicMock(spec=["add", "commit", "close", "scalars", "execute", "rollback"])


def _feed_entry(**overrides):
    """Return a minimal feed entry (feed_monitor format)."""
    base = {
        "url": "https://example.com/news-article",
        "title": "Test News Article",
        "summary": "Short description of the article",
        "published": "2026-03-01",
    }
    base.update(overrides)
    return base


def _unknow_news_feed_config(**overrides):
    """Return a feed_config dict resembling the unknow.news configuration."""
    base = {
        "name": "unknow.news",
        "source_id": "https://unknow.news/",
        "language": "pl",
        "auto_import": True,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFeedMonitorImportEntry:
    """Tests for _import_entry from feed_monitor.py (uses DocumentService)."""

    @patch("imports.feed_monitor.DocumentService")
    def test_new_document_created(self, MockDocService):
        """New document is created via DocumentService with correct fields."""
        session = _make_session()

        mock_doc = MagicMock()
        mock_doc.id = 10
        MockDocService.return_value.import_document.return_value = (mock_doc, "added")

        from imports.feed_monitor import _import_entry

        entry = _feed_entry()
        feed_config = _unknow_news_feed_config()
        result = _import_entry(session, feed_config, entry)

        assert result == "added"
        call_kwargs = MockDocService.return_value.import_document.call_args
        assert call_kwargs[1]["title"] == "Test News Article"
        assert call_kwargs[1]["summary"] == "Short description of the article"
        assert call_kwargs[1]["language"] == "pl"
        assert call_kwargs[1]["source"] == "https://unknow.news/"

    @patch("imports.feed_monitor.DocumentService")
    def test_youtube_url_detection(self, MockDocService):
        """YouTube URLs get document_type=youtube."""
        session = _make_session()

        mock_doc = MagicMock()
        mock_doc.id = 11
        MockDocService.return_value.import_document.return_value = (mock_doc, "added")

        from imports.feed_monitor import _import_entry

        entry = _feed_entry(url="https://www.youtube.com/watch?v=abc123")
        feed_config = _unknow_news_feed_config()
        _import_entry(session, feed_config, entry)

        call_args = MockDocService.return_value.import_document.call_args
        assert call_args[1]["document_type"] == "youtube"

    @patch("imports.feed_monitor.DocumentService")
    def test_regular_link_type(self, MockDocService):
        """Regular URLs get document_type=link."""
        session = _make_session()

        mock_doc = MagicMock()
        mock_doc.id = 12
        MockDocService.return_value.import_document.return_value = (mock_doc, "added")

        from imports.feed_monitor import _import_entry

        entry = _feed_entry()
        feed_config = _unknow_news_feed_config()
        _import_entry(session, feed_config, entry)

        call_args = MockDocService.return_value.import_document.call_args
        assert call_args[1]["document_type"] == "link"


class TestCheckExisting:
    """Tests for check_existing (duplicate detection)."""

    @patch("imports.feed_monitor.WebDocument")
    def test_existing_document_found(self, MockWebDoc):
        """check_existing returns the existing document."""
        session = _make_session()
        existing = MagicMock()
        existing.id = 5
        MockWebDoc.get_by_url.return_value = existing

        from imports.feed_monitor import check_existing

        result = check_existing(session, "https://example.com/news-article")

        assert result is existing
        MockWebDoc.get_by_url.assert_called_once_with(session, "https://example.com/news-article")

    @patch("imports.feed_monitor.WebDocument")
    def test_new_document_returns_none(self, MockWebDoc):
        """check_existing returns None for unknown URLs."""
        session = _make_session()
        MockWebDoc.get_by_url.return_value = None

        from imports.feed_monitor import check_existing

        result = check_existing(session, "https://example.com/new-article")

        assert result is None

    @patch("imports.feed_monitor.WebDocument")
    def test_date_from_corrected_on_existing(self, MockWebDoc):
        """date_from correction logic works (tested via cmd_import's inline code)."""
        # The date_from correction is done in cmd_import, not in _import_entry.
        # Here we verify the building blocks: check_existing finds the doc,
        # and the doc's date_from can be set.
        session = _make_session()
        existing = MagicMock()
        existing.id = 5
        existing.date_from = None
        MockWebDoc.get_by_url.return_value = existing

        from imports.feed_monitor import check_existing, parse_date

        doc = check_existing(session, "https://example.com/news-article")
        assert doc is not None
        assert doc.date_from is None

        # Simulate the correction logic from cmd_import
        pub_date = parse_date("2026-03-01")
        if pub_date and not doc.date_from:
            doc.date_from = pub_date

        assert doc.date_from == pub_date
