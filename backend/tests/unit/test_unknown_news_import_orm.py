"""Unit tests for unknown_news_import.py ORM migration (Story 29.1, Task 2)."""

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
    return MagicMock(spec=["add", "commit", "close", "scalars", "execute"])


def _feed_entry(**overrides):
    """Return a minimal unknow.news feed entry."""
    base = {
        "url": "https://example.com/news-article",
        "title": "Test News Article",
        "info": "Short description of the article",
        "date": "2026-03-01",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestUnknownNewsImportORM:
    """Tests for the ORM-based unknown_news_import logic."""

    @patch("imports.unknown_news_import.WebDocument")
    def test_new_document_created(self, MockWebDoc):
        """New document is created via ORM with correct fields."""
        session = _make_session()
        MockWebDoc.get_by_url.return_value = None

        mock_doc = MagicMock()
        mock_doc.id = 10
        MockWebDoc.return_value = mock_doc

        from imports.unknown_news_import import process_entry

        entry = _feed_entry()
        result = process_entry(entry, session)

        assert result == "added"
        MockWebDoc.get_by_url.assert_called_once_with(session, "https://example.com/news-article")
        session.add.assert_called_once_with(mock_doc)
        session.commit.assert_called_once()
        assert mock_doc.title == "Test News Article"
        assert mock_doc.summary == "Short description of the article"
        assert mock_doc.language == "pl"
        assert mock_doc.source == "https://unknow.news/"

    @patch("imports.unknown_news_import.WebDocument")
    def test_duplicate_skipped(self, MockWebDoc):
        """Existing document is skipped."""
        session = _make_session()
        existing = MagicMock()
        existing.id = 5
        existing.date_from = "2026-02-28"
        MockWebDoc.get_by_url.return_value = existing

        from imports.unknown_news_import import process_entry

        entry = _feed_entry()
        result = process_entry(entry, session)

        assert result == "exists"
        session.add.assert_not_called()

    @patch("imports.unknown_news_import.WebDocument")
    def test_date_from_corrected_on_existing(self, MockWebDoc):
        """date_from is corrected via ORM on existing document missing it."""
        session = _make_session()
        existing = MagicMock()
        existing.id = 5
        existing.date_from = None
        MockWebDoc.get_by_url.return_value = existing

        from imports.unknown_news_import import process_entry

        entry = _feed_entry(date="2026-03-01")
        result = process_entry(entry, session)

        assert result == "exists"
        assert existing.date_from == "2026-03-01"
        session.commit.assert_called_once()

    @patch("imports.unknown_news_import.WebDocument")
    def test_youtube_url_detection(self, MockWebDoc):
        """YouTube URLs get document_type=youtube, document_state=URL_ADDED."""
        session = _make_session()
        MockWebDoc.get_by_url.return_value = None

        mock_doc = MagicMock()
        mock_doc.id = 11
        MockWebDoc.return_value = mock_doc

        from imports.unknown_news_import import process_entry

        entry = _feed_entry(url="https://www.youtube.com/watch?v=abc123")
        process_entry(entry, session)

        assert mock_doc.document_type == "youtube"
        assert mock_doc.document_state == "URL_ADDED"

    @patch("imports.unknown_news_import.WebDocument")
    def test_regular_link_type(self, MockWebDoc):
        """Regular URLs get document_type=link, document_state=READY_FOR_EMBEDDING."""
        session = _make_session()
        MockWebDoc.get_by_url.return_value = None

        mock_doc = MagicMock()
        mock_doc.id = 12
        MockWebDoc.return_value = mock_doc

        from imports.unknown_news_import import process_entry

        entry = _feed_entry()
        process_entry(entry, session)

        assert mock_doc.document_type == "link"
        assert mock_doc.document_state == "READY_FOR_EMBEDDING"
