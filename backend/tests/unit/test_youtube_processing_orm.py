"""Unit tests for youtube_processing.py ORM migration (Story 29.2, Task 1).

Verifies that process_youtube_url():
- Accepts session parameter
- Accepts ai_summary_needed and llm_model parameters (pre-existing bug fix)
- Uses WebDocument ORM model instead of StalkerWebDocumentDB
- Calls session.commit() instead of save()
- Returns WebDocument instance

Pre-mocks boto3 so that importing library.youtube_processing (which
transitively imports boto3 via text_detect_language) does not fail
when botocore/s3transfer are broken or unavailable.
"""

import sys
from types import ModuleType
from unittest.mock import MagicMock

import pytest

sa = pytest.importorskip("sqlalchemy")

# ---------------------------------------------------------------------------
# Pre-mock boto3 and transitive deps before any library import
# ---------------------------------------------------------------------------
_BOTO_MODS = [
    "boto3", "boto3.dynamodb", "boto3.dynamodb.conditions",
    "botocore", "botocore.exceptions", "botocore.compat",
    "s3transfer",
]
for _mod_name in _BOTO_MODS:
    if _mod_name not in sys.modules:
        _mock_mod = MagicMock(spec=ModuleType)
        if _mod_name == "botocore.exceptions":
            _mock_mod.ClientError = type("ClientError", (Exception,), {})
        sys.modules[_mod_name] = _mock_mod

from unittest.mock import patch, PropertyMock  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_session():
    session = MagicMock(spec=Session)
    return session


@pytest.fixture
def mock_web_document():
    """A mock WebDocument ORM instance."""
    from library.models.stalker_document_status import StalkerDocumentStatus
    from library.models.stalker_document_type import StalkerDocumentType

    doc = MagicMock()
    doc.id = 42
    doc.url = "https://www.youtube.com/watch?v=test123"
    doc.document_state = StalkerDocumentStatus.URL_ADDED
    doc.document_type = StalkerDocumentType.youtube
    doc.language = "en"
    doc.chapter_list = None
    doc.title = "Test Video"
    doc.text = "some text"
    doc.text_raw = "some text"
    doc.transcript_job_id = None
    doc.youtube_captions = None
    doc.summary = None
    doc.original_id = None
    doc.document_length = None
    doc.source = "own"
    doc.note = None
    return doc


# ---------------------------------------------------------------------------
# Test: Function signature
# ---------------------------------------------------------------------------

class TestProcessYoutubeUrlSignature:
    """Verify function accepts required parameters."""

    def test_session_parameter_in_signature(self):
        """process_youtube_url must accept session as first parameter."""
        import inspect
        from library.youtube_processing import process_youtube_url
        sig = inspect.signature(process_youtube_url)
        params = list(sig.parameters.keys())
        assert "session" in params, "session parameter missing from process_youtube_url signature"

    def test_ai_summary_needed_parameter(self):
        """process_youtube_url must accept ai_summary_needed parameter (bug fix)."""
        import inspect
        from library.youtube_processing import process_youtube_url
        sig = inspect.signature(process_youtube_url)
        assert "ai_summary_needed" in sig.parameters

    def test_llm_model_parameter(self):
        """process_youtube_url must accept llm_model parameter (bug fix)."""
        import inspect
        from library.youtube_processing import process_youtube_url
        sig = inspect.signature(process_youtube_url)
        assert "llm_model" in sig.parameters

    def test_return_annotation_is_web_document(self):
        """Return type annotation should be WebDocument."""
        import inspect
        from library.youtube_processing import process_youtube_url
        sig = inspect.signature(process_youtube_url)
        # Check that return annotation references WebDocument (not StalkerWebDocumentDB)
        ret = sig.return_annotation
        assert ret is not inspect.Parameter.empty
        # Allow both string annotation and actual class
        ret_name = ret if isinstance(ret, str) else getattr(ret, "__name__", str(ret))
        assert "WebDocument" in str(ret_name), f"Expected WebDocument return type, got {ret_name}"


# ---------------------------------------------------------------------------
# Test: New document creation via ORM
# ---------------------------------------------------------------------------

class TestNewDocumentCreation:
    """Verify new YouTube documents are created via ORM."""

    @patch("library.youtube_processing.StalkerYoutubeFile")
    @patch("library.youtube_processing.WebDocument")
    def test_new_document_uses_orm(self, MockWebDocument, MockYoutubeFile, mock_session):
        """When URL not found, should create WebDocument and session.add()."""
        from library.youtube_processing import process_youtube_url
        from library.models.stalker_document_status import StalkerDocumentStatus

        # URL not found -> get_by_url returns None
        MockWebDocument.get_by_url.return_value = None

        # New doc mock
        new_doc = MagicMock()
        new_doc.id = 1
        new_doc.url = "https://www.youtube.com/watch?v=abc"
        new_doc.document_state = StalkerDocumentStatus.EMBEDDING_EXIST  # skip processing
        new_doc.language = "en"
        new_doc.chapter_list = None
        new_doc.transcript_job_id = None
        MockWebDocument.return_value = new_doc

        # Youtube file mock - make it invalid to short-circuit
        yt_file = MagicMock()
        yt_file.valid = False
        yt_file.error = "test error"
        MockYoutubeFile.return_value = yt_file

        process_youtube_url(
            session=mock_session,
            youtube_url="https://www.youtube.com/watch?v=abc",
        )

        # Verify ORM usage
        MockWebDocument.get_by_url.assert_called_once_with(mock_session, "https://www.youtube.com/watch?v=abc")
        mock_session.add.assert_called_once_with(new_doc)
        mock_session.commit.assert_called()

    @patch("library.youtube_processing.StalkerYoutubeFile")
    @patch("library.youtube_processing.WebDocument")
    def test_existing_document_no_add(self, MockWebDocument, MockYoutubeFile, mock_session):
        """When URL exists, should NOT session.add() — just use existing doc."""
        from library.youtube_processing import process_youtube_url
        from library.models.stalker_document_status import StalkerDocumentStatus

        existing_doc = MagicMock()
        existing_doc.id = 42
        existing_doc.url = "https://www.youtube.com/watch?v=abc"
        existing_doc.document_state = StalkerDocumentStatus.EMBEDDING_EXIST
        existing_doc.language = "en"
        existing_doc.chapter_list = None
        existing_doc.transcript_job_id = None
        MockWebDocument.get_by_url.return_value = existing_doc

        returned = process_youtube_url(
            session=mock_session,
            youtube_url="https://www.youtube.com/watch?v=abc",
        )

        # Should NOT add — doc already exists
        mock_session.add.assert_not_called()
        assert returned is existing_doc


# ---------------------------------------------------------------------------
# Test: No legacy imports
# ---------------------------------------------------------------------------

class TestNoLegacyImports:
    """Verify youtube_processing.py no longer imports legacy classes."""

    def test_no_stalker_web_document_db_import(self):
        """StalkerWebDocumentDB should not be imported."""
        import library.youtube_processing as mod
        assert not hasattr(mod, "StalkerWebDocumentDB"), \
            "youtube_processing.py still imports StalkerWebDocumentDB"

    def test_imports_web_document(self):
        """WebDocument should be imported from library.db.models."""
        import library.youtube_processing as mod
        assert hasattr(mod, "WebDocument"), \
            "youtube_processing.py must import WebDocument from library.db.models"


# ---------------------------------------------------------------------------
# Test: session.commit() used instead of save()
# ---------------------------------------------------------------------------

class TestSessionCommit:
    """Verify session.commit() is called, not doc.save()."""

    @patch("library.youtube_processing.StalkerYoutubeFile")
    @patch("library.youtube_processing.WebDocument")
    def test_commit_called_for_metadata_update(self, MockWebDocument, MockYoutubeFile, mock_session):
        """When metadata is updated, session.commit() should be called."""
        from library.youtube_processing import process_youtube_url
        from library.models.stalker_document_status import StalkerDocumentStatus

        doc = MagicMock()
        doc.id = 1
        doc.url = "https://www.youtube.com/watch?v=abc"
        doc.document_state = StalkerDocumentStatus.URL_ADDED
        doc.language = "en"
        doc.chapter_list = None
        doc.transcript_job_id = None
        MockWebDocument.get_by_url.return_value = doc

        yt_file = MagicMock()
        yt_file.valid = True
        yt_file.can_pytube = True
        yt_file.title = "Test"
        yt_file.url = "https://www.youtube.com/watch?v=abc"
        yt_file.video_id = "abc"
        yt_file.text = "text"
        yt_file.length_seconds = 120
        yt_file.description = "desc"
        yt_file.length_minutes = 2
        yt_file.path = "/tmp/test.mp4"
        yt_file.filename = "test.mp4"
        MockYoutubeFile.return_value = yt_file

        # Mock YouTubeTranscriptApi to raise to short-circuit captions
        with patch("library.youtube_processing.YouTubeTranscriptApi") as MockYTT:
            mock_ytt = MagicMock()
            mock_ytt.list.side_effect = Exception("test skip")
            MockYTT.return_value = mock_ytt

            # Skip external transcription by setting doc state to something final
            def set_state(val):
                doc.document_state = val
            type(doc).document_state = PropertyMock(side_effect=[
                StalkerDocumentStatus.URL_ADDED,   # initial check force_reprocess
                StalkerDocumentStatus.URL_ADDED,   # metadata fetch check
                StalkerDocumentStatus.NEED_TRANSCRIPTION,  # after set
                StalkerDocumentStatus.NEED_TRANSCRIPTION,  # captions check
                StalkerDocumentStatus.EMBEDDING_EXIST,     # external transcription check - skip
            ])

            try:
                process_youtube_url(
                    session=mock_session,
                    youtube_url="https://www.youtube.com/watch?v=abc",
                )
            except (StopIteration, Exception):
                pass

        # session.commit() should have been called (not doc.save())
        assert mock_session.commit.called, "session.commit() was not called"
        assert not doc.save.called, "doc.save() should not be called — use session.commit()"
