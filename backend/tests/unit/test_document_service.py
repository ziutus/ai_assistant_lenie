"""Unit tests for DocumentService (Story 32.1).

All tests use mocked sessions — no database required.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("sqlalchemy")

from library.document_service import DocumentService
from library.db.models import WebDocument


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session():
    """Return a mock SQLAlchemy session."""
    session = MagicMock()
    return session


def _make_doc(**overrides):
    """Return a WebDocument with safe defaults for testing."""
    defaults = {
        "url": "https://example.com",
        "document_type": "webpage",
        "document_state": "URL_ADDED",
        "document_state_error": "NONE",
        "id": 42,
    }
    defaults.update(overrides)
    doc = MagicMock(spec=WebDocument)
    for k, v in defaults.items():
        setattr(doc, k, v)
    doc.dict.return_value = defaults
    return doc


# ---------------------------------------------------------------------------
# Tests: __init__
# ---------------------------------------------------------------------------


class TestDocumentServiceInit:
    def test_stores_session(self):
        session = _make_session()
        service = DocumentService(session)
        assert service.session is session

    def test_creates_repo(self):
        session = _make_session()
        service = DocumentService(session)
        assert service.repo is not None


# ---------------------------------------------------------------------------
# Tests: create_document
# ---------------------------------------------------------------------------


class TestCreateDocument:
    @patch("library.document_service.load_config")
    def test_create_document_basic(self, mock_config):
        """Create a basic link document (no S3 storage)."""
        cfg = MagicMock()
        cfg.get.return_value = None  # no S3
        mock_config.return_value = cfg

        session = _make_session()
        service = DocumentService(session)

        service.create_document(url="https://example.com", url_type="link", title="Test")

        session.add.assert_called_once()
        session.commit.assert_called_once()

    @patch("library.document_service.load_config")
    def test_create_document_missing_url(self, mock_config):
        """Raise ValueError when url is missing."""
        session = _make_session()
        service = DocumentService(session)

        with pytest.raises(ValueError, match="Missing required"):
            service.create_document(url="", url_type="link")

    @patch("library.document_service.load_config")
    def test_create_document_missing_type(self, mock_config):
        """Raise ValueError when url_type is missing."""
        session = _make_session()
        service = DocumentService(session)

        with pytest.raises(ValueError, match="Missing required"):
            service.create_document(url="https://example.com", url_type="")

    @patch("library.document_service.load_config")
    def test_create_document_webpage_with_local_storage(self, mock_config):
        """Webpage type triggers file storage (local when no S3 bucket)."""
        cfg = MagicMock()
        cfg.get.return_value = None  # no S3
        mock_config.return_value = cfg

        session = _make_session()
        service = DocumentService(session)

        with patch.object(service, "_store_file") as mock_store:
            service.create_document(
                url="https://example.com",
                url_type="webpage",
                text="some text",
                html="<p>hi</p>",
            )
            assert mock_store.call_count == 2  # text + html

    @patch("library.document_service.load_config")
    def test_create_document_webpage_no_html(self, mock_config):
        """Webpage with text but no html — only one file stored."""
        cfg = MagicMock()
        cfg.get.return_value = None
        mock_config.return_value = cfg

        session = _make_session()
        service = DocumentService(session)

        with patch.object(service, "_store_file") as mock_store:
            service.create_document(
                url="https://example.com",
                url_type="webpage",
                text="some text",
            )
            assert mock_store.call_count == 1

    @patch("library.document_service.load_config")
    def test_create_document_with_s3(self, mock_config):
        """When S3 bucket configured, _store_file is called with S3 params."""
        cfg = MagicMock()
        cfg.get.return_value = "my-bucket"
        mock_config.return_value = cfg

        mock_boto3 = MagicMock()
        session = _make_session()
        service = DocumentService(session)

        with patch.dict(sys.modules, {"boto3": mock_boto3}), \
             patch.object(service, "_store_file") as mock_store:
            service.create_document(
                url="https://example.com",
                url_type="webpage",
                text="text content",
                html="<p>html</p>",
            )

            assert mock_store.call_count == 2
            # Verify S3 params are passed (use_s3=True, bucket="my-bucket")
            for call in mock_store.call_args_list:
                assert call[0][3] is True  # use_s3
                assert call[0][5] == "my-bucket"  # bucket_name

    @patch("library.document_service.load_config")
    def test_create_document_invalid_type(self, mock_config):
        """Invalid document type raises ValueError (from set_document_type)."""
        cfg = MagicMock()
        cfg.get.return_value = None
        mock_config.return_value = cfg

        session = _make_session()
        service = DocumentService(session)

        with pytest.raises(ValueError):
            service.create_document(url="https://example.com", url_type="invalid_type")


# ---------------------------------------------------------------------------
# Tests: save_document
# ---------------------------------------------------------------------------


class TestSaveDocument:
    def test_save_existing_by_id(self):
        """Save updates an existing document found by ID."""
        session = _make_session()
        doc = _make_doc()

        with patch.object(WebDocument, "get_by_id", return_value=doc):
            service = DocumentService(session)
            result = service.save_document(url="https://example.com", link_id=42, title="New Title")

        assert result is doc
        session.commit.assert_called_once()

    def test_save_existing_by_url(self):
        """Save updates an existing document found by URL."""
        session = _make_session()
        doc = _make_doc()

        with patch.object(WebDocument, "get_by_id", return_value=None), \
             patch.object(WebDocument, "get_by_url", return_value=doc):
            service = DocumentService(session)
            result = service.save_document(url="https://example.com", title="Updated")

        assert result is doc

    def test_save_creates_new_when_not_found(self):
        """Save creates a new document when not found by id or url."""
        session = _make_session()

        with patch.object(WebDocument, "get_by_id", return_value=None), \
             patch.object(WebDocument, "get_by_url", return_value=None):
            service = DocumentService(session)
            service.save_document(url="https://new.example.com")

        session.add.assert_called_once()
        session.commit.assert_called_once()

    def test_save_missing_url(self):
        """Raise ValueError when url is empty."""
        session = _make_session()
        service = DocumentService(session)

        with pytest.raises(ValueError, match="Missing data"):
            service.save_document(url="")

    def test_save_with_document_type(self):
        """Save with document_type calls set_document_type."""
        session = _make_session()
        doc = _make_doc()

        with patch.object(WebDocument, "get_by_id", return_value=doc):
            service = DocumentService(session)
            service.save_document(url="https://example.com", link_id=42, document_type="link")

        doc.set_document_type.assert_called_once_with("link")

    def test_save_with_invalid_document_type(self):
        """Save with invalid document_type raises ValueError."""
        session = _make_session()
        doc = _make_doc()
        doc.set_document_type.side_effect = ValueError("invalid type")

        with patch.object(WebDocument, "get_by_id", return_value=doc):
            service = DocumentService(session)
            with pytest.raises(ValueError):
                service.save_document(url="https://example.com", link_id=42, document_type="invalid")

    def test_save_with_state_transition(self):
        """Save with document_state calls set_document_state."""
        session = _make_session()
        doc = _make_doc()

        with patch.object(WebDocument, "get_by_id", return_value=doc):
            service = DocumentService(session)
            service.save_document(url="https://example.com", link_id=42, document_state="NEED_MANUAL_REVIEW")

        doc.set_document_state.assert_called_once_with("NEED_MANUAL_REVIEW")


# ---------------------------------------------------------------------------
# Tests: delete_document
# ---------------------------------------------------------------------------


class TestDeleteDocument:
    def test_delete_existing(self):
        """Delete an existing document returns True."""
        session = _make_session()
        doc = _make_doc()

        with patch.object(WebDocument, "get_by_id", return_value=doc):
            service = DocumentService(session)
            result = service.delete_document(42)

        assert result is True
        session.delete.assert_called_once_with(doc)
        session.commit.assert_called_once()

    def test_delete_not_found(self):
        """Delete a non-existent document returns False."""
        session = _make_session()

        with patch.object(WebDocument, "get_by_id", return_value=None):
            service = DocumentService(session)
            result = service.delete_document(999)

        assert result is False
        session.delete.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: get_document
# ---------------------------------------------------------------------------


class TestGetDocument:
    def test_get_existing(self):
        """Get an existing document with neighbors."""
        session = _make_session()
        doc = _make_doc()

        with patch.object(WebDocument, "get_by_id", return_value=doc) as mock_get:
            service = DocumentService(session)
            result = service.get_document(42)

        assert result is doc
        mock_get.assert_called_once_with(session, 42, reach=True)

    def test_get_not_found(self):
        """Get a non-existent document returns None."""
        session = _make_session()

        with patch.object(WebDocument, "get_by_id", return_value=None):
            service = DocumentService(session)
            result = service.get_document(999)

        assert result is None

    def test_get_without_reach(self):
        """Get document without neighbor population."""
        session = _make_session()
        doc = _make_doc()

        with patch.object(WebDocument, "get_by_id", return_value=doc) as mock_get:
            service = DocumentService(session)
            service.get_document(42, reach=False)

        mock_get.assert_called_once_with(session, 42, reach=False)


# ---------------------------------------------------------------------------
# Tests: download_and_parse
# ---------------------------------------------------------------------------


class TestDownloadAndParse:
    @patch("library.document_service.webpage_raw_parse")
    @patch("library.document_service.download_raw_html")
    def test_download_success(self, mock_download, mock_parse):
        """Successful download returns parsed content dict."""
        mock_download.return_value = "<html>content</html>"
        mock_result = MagicMock()
        mock_result.text = "parsed text"
        mock_result.title = "Page Title"
        mock_result.summary = "Summary"
        mock_result.language = "en"
        mock_parse.return_value = mock_result

        session = _make_session()
        service = DocumentService(session)
        result = service.download_and_parse("https://example.com")

        assert result["text"] == "parsed text"
        assert result["title"] == "Page Title"
        assert result["summary"] == "Summary"
        assert result["language"] == "en"

    @patch("library.document_service.download_raw_html")
    def test_download_empty_response(self, mock_download):
        """Raise RuntimeError when download returns empty."""
        mock_download.return_value = None

        session = _make_session()
        service = DocumentService(session)

        with pytest.raises(RuntimeError, match="empty response"):
            service.download_and_parse("https://example.com")


# ---------------------------------------------------------------------------
# Tests: clean_text
# ---------------------------------------------------------------------------


class TestCleanText:
    @patch("library.document_service.webpage_text_clean")
    def test_clean_delegates(self, mock_clean):
        """clean_text delegates to webpage_text_clean."""
        mock_clean.return_value = "cleaned text"

        session = _make_session()
        service = DocumentService(session)
        result = service.clean_text("https://example.com", "raw text")

        assert result == "cleaned text"
        mock_clean.assert_called_once_with("https://example.com", "raw text")


# ---------------------------------------------------------------------------
# Tests: split_for_embedding
# ---------------------------------------------------------------------------


class TestSplitForEmbedding:
    @patch("library.document_service.split_text_for_embedding")
    @patch("library.document_service.chapters_text_to_list")
    def test_split_with_chapters(self, mock_chapters, mock_split):
        """split_for_embedding passes chapter titles to split function."""
        mock_chapters.return_value = [{"title": "Ch1"}, {"title": "Ch2"}]
        mock_split.return_value = ["chunk1", "chunk2"]

        session = _make_session()
        service = DocumentService(session)
        result = service.split_for_embedding("long text", "chapter data")

        assert result == ["chunk1", "chunk2"]
        mock_chapters.assert_called_once_with("chapter data")
        mock_split.assert_called_once_with("long text", ["Ch1", "Ch2"])

    @patch("library.document_service.split_text_for_embedding")
    @patch("library.document_service.chapters_text_to_list")
    def test_split_no_chapters(self, mock_chapters, mock_split):
        """split_for_embedding works without chapters."""
        mock_chapters.return_value = []
        mock_split.return_value = ["single chunk"]

        session = _make_session()
        service = DocumentService(session)
        result = service.split_for_embedding("text", None)

        assert result == ["single chunk"]
        mock_chapters.assert_called_once_with(None)
        mock_split.assert_called_once_with("text", [])


# ---------------------------------------------------------------------------
# Tests: _store_file (private, but critical)
# ---------------------------------------------------------------------------


class TestStoreFile:
    def test_store_s3(self):
        """S3 storage calls put_object."""
        s3_client = MagicMock()
        session = _make_session()
        service = DocumentService(session)

        service._store_file("uid123", "txt", "content", True, s3_client, "my-bucket")

        s3_client.put_object.assert_called_once_with(Bucket="my-bucket", Key="uid123.txt", Body="content")

    def test_store_s3_failure(self):
        """S3 upload failure raises RuntimeError."""
        s3_client = MagicMock()
        s3_client.put_object.side_effect = Exception("S3 error")
        session = _make_session()
        service = DocumentService(session)

        with pytest.raises(RuntimeError, match="Failed to upload"):
            service._store_file("uid123", "txt", "content", True, s3_client, "my-bucket")

    @patch("builtins.open", create=True)
    @patch("library.document_service.os.makedirs")
    def test_store_local(self, mock_makedirs, mock_open):
        """Local storage writes file to /app/data/."""
        session = _make_session()
        service = DocumentService(session)

        service._store_file("uid123", "html", "<p>hi</p>", False, None, None)

        mock_makedirs.assert_called_once_with("/app/data", exist_ok=True)
        mock_open.assert_called_once_with("/app/data/uid123.html", "w", encoding="utf-8")

    @patch("builtins.open", side_effect=OSError("disk full"))
    @patch("library.document_service.os.makedirs")
    def test_store_local_failure(self, mock_makedirs, mock_open):
        """Local storage failure raises RuntimeError."""
        session = _make_session()
        service = DocumentService(session)

        with pytest.raises(RuntimeError, match="Failed to save"):
            service._store_file("uid123", "txt", "content", False, None, None)


# ---------------------------------------------------------------------------
# Tests: import_document
# ---------------------------------------------------------------------------


class TestImportDocument:
    def test_import_new_document(self):
        """Import a new document — returns (doc, 'added')."""
        session = _make_session()
        service = DocumentService(session)

        with patch.object(WebDocument, "get_by_url", return_value=None):
            doc, status = service.import_document(
                url="https://example.com/article",
                document_type="link",
                title="Test Article",
                language="pl",
                source="unknow.news",
            )

        assert status == "added"
        assert doc.url == "https://example.com/article"
        session.add.assert_called_once()
        session.commit.assert_called_once()

    def test_import_duplicate_skipped(self):
        """Import existing URL — returns (existing, 'skipped')."""
        session = _make_session()
        existing_doc = _make_doc(url="https://example.com/dup")

        with patch.object(WebDocument, "get_by_url", return_value=existing_doc):
            service = DocumentService(session)
            doc, status = service.import_document(
                url="https://example.com/dup",
                document_type="link",
            )

        assert status == "skipped"
        assert doc is existing_doc
        session.add.assert_not_called()

    def test_import_with_text_and_html(self):
        """Import with text/html sets content directly on model (no S3)."""
        session = _make_session()

        with patch.object(WebDocument, "get_by_url", return_value=None):
            service = DocumentService(session)
            doc, status = service.import_document(
                url="https://example.com/page",
                document_type="webpage",
                text="some text content",
                text_raw="<p>html content</p>",
            )

        assert status == "added"
        assert doc.text == "some text content"
        assert doc.text_raw == "<p>html content</p>"

    def test_import_custom_document_state(self):
        """Import with custom document_state sets it correctly."""
        session = _make_session()

        with patch.object(WebDocument, "get_by_url", return_value=None):
            service = DocumentService(session)
            doc, status = service.import_document(
                url="https://example.com/ready",
                document_type="link",
                document_state="READY_FOR_EMBEDDING",
            )

        assert status == "added"

    def test_import_default_state_url_added(self):
        """Import without document_state defaults to URL_ADDED."""
        session = _make_session()

        with patch.object(WebDocument, "get_by_url", return_value=None):
            service = DocumentService(session)
            doc, status = service.import_document(
                url="https://example.com/default",
                document_type="link",
            )

        assert status == "added"

    def test_import_missing_url_raises(self):
        """Import with empty url raises ValueError."""
        session = _make_session()
        service = DocumentService(session)

        with pytest.raises(ValueError, match="Missing required"):
            service.import_document(url="", document_type="link")

    def test_import_various_metadata(self):
        """Import with all metadata fields sets them on the document."""
        session = _make_session()

        with patch.object(WebDocument, "get_by_url", return_value=None):
            service = DocumentService(session)
            doc, status = service.import_document(
                url="https://example.com/full",
                document_type="webpage",
                title="Full Title",
                language="en",
                source="feed",
                note="some note",
                uuid="abc-123",
                chapter_list=True,
                summary="A summary",
                paywall=True,
                date_from="2026-01-01",
                project="test-project",
                ai_summary_needed=True,
            )

        assert status == "added"
        assert doc.title == "Full Title"
        assert doc.language == "en"
        assert doc.source == "feed"
        assert doc.note == "some note"
        assert doc.uuid == "abc-123"
        assert doc.summary == "A summary"
        assert doc.paywall is True
        assert doc.project == "test-project"

    def test_import_skip_if_exists_false(self):
        """Import with skip_if_exists=False creates even if URL exists."""
        session = _make_session()
        existing_doc = _make_doc(url="https://example.com/dup2")

        with patch.object(WebDocument, "get_by_url", return_value=existing_doc) as mock_get:
            service = DocumentService(session)
            doc, status = service.import_document(
                url="https://example.com/dup2",
                document_type="link",
                skip_if_exists=False,
            )

        assert status == "added"
        mock_get.assert_not_called()
        session.add.assert_called_once()

    def test_import_none_metadata_ignored(self):
        """Import ignores None metadata values."""
        session = _make_session()

        with patch.object(WebDocument, "get_by_url", return_value=None):
            service = DocumentService(session)
            doc, status = service.import_document(
                url="https://example.com/none",
                document_type="link",
                title=None,
                note=None,
            )

        assert status == "added"
