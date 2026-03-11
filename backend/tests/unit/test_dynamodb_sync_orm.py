"""Unit tests for dynamodb_sync.py ORM migration (Story 29.1, Task 1)."""

from unittest.mock import MagicMock, patch

import pytest

sa = pytest.importorskip("sqlalchemy")

from library.models.stalker_document_status import StalkerDocumentStatus  # noqa: E402, F401


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_session():
    """Return a mock SQLAlchemy Session."""
    session = MagicMock(spec=["add", "commit", "close", "scalars", "execute"])
    return session


def _dynamo_item(**overrides):
    """Return a minimal DynamoDB item dict."""
    base = {
        "url": "https://example.com/article",
        "title": "Test Article",
        "language": "en",
        "source": "own",
        "type": "link",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Tests for sync_item_to_postgres
# ---------------------------------------------------------------------------


class TestSyncItemToPostgres:
    """Tests for the ORM-based sync_item_to_postgres function."""

    @patch("imports.dynamodb_sync.WebDocument")
    def test_new_document_added(self, MockWebDoc):
        """New document is created via ORM and committed."""
        session = _make_session()
        MockWebDoc.get_by_url.return_value = None

        mock_doc = MagicMock()
        mock_doc.id = 42
        mock_doc.title = "Test Article"
        MockWebDoc.return_value = mock_doc

        from imports.dynamodb_sync import sync_item_to_postgres

        item = _dynamo_item()
        result = sync_item_to_postgres(item, None, None, dry_run=False, session=session)

        assert result == "added"
        MockWebDoc.get_by_url.assert_called_once_with(session, "https://example.com/article")
        session.add.assert_called_once_with(mock_doc)
        session.commit.assert_called_once()

    @patch("imports.dynamodb_sync.WebDocument")
    def test_duplicate_skipped(self, MockWebDoc):
        """Existing document is skipped (not inserted)."""
        session = _make_session()
        existing = MagicMock()
        existing.id = 99
        MockWebDoc.get_by_url.return_value = existing

        from imports.dynamodb_sync import sync_item_to_postgres

        item = _dynamo_item()
        result = sync_item_to_postgres(item, None, None, dry_run=False, session=session)

        assert result == "skipped"
        session.add.assert_not_called()
        session.commit.assert_not_called()

    @patch("imports.dynamodb_sync.WebDocument")
    def test_created_at_set_via_orm(self, MockWebDoc):
        """created_at is set via ORM attribute (no raw SQL)."""
        session = _make_session()
        MockWebDoc.get_by_url.return_value = None

        mock_doc = MagicMock()
        mock_doc.id = 1
        mock_doc.title = "Title"
        MockWebDoc.return_value = mock_doc

        from imports.dynamodb_sync import sync_item_to_postgres

        item = _dynamo_item(created_at="2026-01-15T10:30:00")
        sync_item_to_postgres(item, None, None, dry_run=False, session=session)

        assert mock_doc.created_at == "2026-01-15T10:30:00"

    @patch("imports.dynamodb_sync.WebDocument")
    def test_chapter_list_set_via_orm(self, MockWebDoc):
        """chapter_list is set via ORM attribute (no raw SQL)."""
        session = _make_session()
        MockWebDoc.get_by_url.return_value = None

        mock_doc = MagicMock()
        mock_doc.id = 1
        mock_doc.title = "Title"
        MockWebDoc.return_value = mock_doc

        from imports.dynamodb_sync import sync_item_to_postgres

        item = _dynamo_item(chapter_list="ch1;ch2;ch3")
        sync_item_to_postgres(item, None, None, dry_run=False, session=session)

        assert mock_doc.chapter_list == "ch1;ch2;ch3"

    @patch("imports.dynamodb_sync.WebDocument")
    def test_document_state_with_s3_content(self, MockWebDoc):
        """document_state is DOCUMENT_INTO_DATABASE when S3 content exists."""
        session = _make_session()
        MockWebDoc.get_by_url.return_value = None

        mock_doc = MagicMock()
        mock_doc.id = 1
        mock_doc.title = "Title"
        MockWebDoc.return_value = mock_doc

        from imports.dynamodb_sync import sync_item_to_postgres

        item = _dynamo_item()
        sync_item_to_postgres(item, "some text", "<html>", dry_run=False, session=session)

        assert mock_doc.document_state == "DOCUMENT_INTO_DATABASE"

    @patch("imports.dynamodb_sync.WebDocument")
    def test_document_state_without_content(self, MockWebDoc):
        """document_state is URL_ADDED when no S3 content."""
        session = _make_session()
        MockWebDoc.get_by_url.return_value = None

        mock_doc = MagicMock()
        mock_doc.id = 1
        mock_doc.title = "Title"
        MockWebDoc.return_value = mock_doc

        from imports.dynamodb_sync import sync_item_to_postgres

        item = _dynamo_item()
        sync_item_to_postgres(item, None, None, dry_run=False, session=session)

        assert mock_doc.document_state == "URL_ADDED"

    @patch("imports.dynamodb_sync.WebDocument")
    def test_dry_run_no_db_writes(self, MockWebDoc):
        """dry_run mode does not write to DB."""
        session = _make_session()

        from imports.dynamodb_sync import sync_item_to_postgres

        item = _dynamo_item()
        result = sync_item_to_postgres(item, None, None, dry_run=True, session=session)

        assert result == "added"
        session.add.assert_not_called()
        session.commit.assert_not_called()
        MockWebDoc.get_by_url.assert_not_called()
