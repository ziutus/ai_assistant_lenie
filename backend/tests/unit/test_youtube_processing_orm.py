"""Unit tests for youtube_processing.py ORM migration (Story 29.2, Task 1).

Verifies that process_youtube_url():
- Accepts session parameter
- Accepts ai_summary_needed and llm_model parameters (pre-existing bug fix)
- Uses Document ORM model instead of StalkerWebDocumentDB
- Calls session.commit() instead of save()
- Returns Document instance

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


@pytest.fixture(autouse=True)
def captions_events():
    """Captions attempts are logged to external_service_events; never touch a database here."""
    with patch("library.external_service_events.record_external_service_event") as record:
        yield record


@pytest.fixture
def mock_web_document():
    """A mock Document ORM instance."""
    from library.models.stalker_document_status import StalkerDocumentStatus
    from library.models.stalker_document_type import StalkerDocumentType

    doc = MagicMock()
    doc.id = 42
    doc.url = "https://www.youtube.com/watch?v=test123"
    doc.processing_status = StalkerDocumentStatus.URL_ADDED
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
        """Return type annotation should be Document."""
        import inspect
        from library.youtube_processing import process_youtube_url
        sig = inspect.signature(process_youtube_url)
        # Check that return annotation references Document (not StalkerWebDocumentDB)
        ret = sig.return_annotation
        assert ret is not inspect.Parameter.empty
        # Allow both string annotation and actual class
        ret_name = ret if isinstance(ret, str) else getattr(ret, "__name__", str(ret))
        assert "Document" in str(ret_name), f"Expected Document return type, got {ret_name}"


# ---------------------------------------------------------------------------
# Test: New document creation via ORM
# ---------------------------------------------------------------------------

class TestNewDocumentCreation:
    """Verify new YouTube documents are created via ORM."""

    @patch("library.youtube_processing.StalkerYoutubeFile")
    @patch("library.youtube_processing.Document")
    def test_new_document_uses_orm(self, MockWebDocument, MockYoutubeFile, mock_session):
        """When URL not found, should create Document and session.add()."""
        from library.youtube_processing import process_youtube_url
        from library.models.stalker_document_status import StalkerDocumentStatus

        # URL not found -> get_by_url returns None
        MockWebDocument.get_by_url.return_value = None

        # New doc mock
        new_doc = MagicMock()
        new_doc.id = 1
        new_doc.url = "https://www.youtube.com/watch?v=abc"
        new_doc.processing_status = StalkerDocumentStatus.EMBEDDING_EXIST  # skip processing
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
    @patch("library.youtube_processing.Document")
    def test_existing_document_no_add(self, MockWebDocument, MockYoutubeFile, mock_session):
        """When URL exists, should NOT session.add() — just use existing doc."""
        from library.youtube_processing import process_youtube_url
        from library.models.stalker_document_status import StalkerDocumentStatus

        existing_doc = MagicMock()
        existing_doc.id = 42
        existing_doc.url = "https://www.youtube.com/watch?v=abc"
        existing_doc.processing_status = StalkerDocumentStatus.EMBEDDING_EXIST
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
        """Document should be imported from library.db.models."""
        import library.youtube_processing as mod
        assert hasattr(mod, "Document"), \
            "youtube_processing.py must import Document from library.db.models"


# ---------------------------------------------------------------------------
# Test: session.commit() used instead of save()
# ---------------------------------------------------------------------------

class TestSessionCommit:
    """Verify session.commit() is called, not doc.save()."""

    @patch("library.youtube_processing.StalkerYoutubeFile")
    @patch("library.youtube_processing.Document")
    def test_commit_called_for_metadata_update(self, MockWebDocument, MockYoutubeFile, mock_session):
        """When metadata is updated, session.commit() should be called."""
        from library.youtube_processing import process_youtube_url
        from library.models.stalker_document_status import StalkerDocumentStatus

        doc = MagicMock()
        doc.id = 1
        doc.url = "https://www.youtube.com/watch?v=abc"
        doc.processing_status = StalkerDocumentStatus.URL_ADDED
        doc.language = "en"
        doc.chapter_list = None
        doc.transcript_job_id = None
        MockWebDocument.get_by_url.return_value = doc

        yt_file = MagicMock()
        yt_file.valid = True
        yt_file.metadata_available = True
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
                doc.processing_status = val
            type(doc).processing_status = PropertyMock(side_effect=[
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


# ---------------------------------------------------------------------------
# Test: processing_error_code is cleared on a successful captions fetch
# ---------------------------------------------------------------------------

class TestDocumentStateErrorClearedOnSuccess:
    """A stale processing_error_code from a previous failed attempt must not
    survive a subsequent successful captions fetch (regression: it used to be
    sticky forever — see CAPTIONS_FETCH_ERROR left behind after a retry succeeded)."""

    @patch("library.youtube_processing.youtube_titles_to_text")
    @patch("library.youtube_processing.compare_language")
    @patch("library.youtube_processing.text_language_detect")
    @patch("library.youtube_processing.StalkerYoutubeFile")
    @patch("library.youtube_processing.Document")
    def test_captions_success_clears_stale_error(
        self, MockWebDocument, MockYoutubeFile, mock_detect, mock_compare, mock_titles_to_text, mock_session
    ):
        from library.youtube_processing import process_youtube_url
        from library.models.stalker_document_status import StalkerDocumentStatus
        from library.models.stalker_document_status_error import StalkerDocumentStatusError

        doc = MagicMock()
        doc.id = 1
        doc.url = "https://www.youtube.com/watch?v=abc"
        doc.processing_status = StalkerDocumentStatus.NEED_TRANSCRIPTION.name
        # Stale error left over from an earlier failed attempt (the bug this test guards against)
        doc.processing_error_code = StalkerDocumentStatusError.CAPTIONS_FETCH_ERROR.name
        doc.language = "pl"
        doc.chapter_list = None
        doc.transcript_job_id = None
        MockWebDocument.get_by_url.return_value = doc

        yt_file = MagicMock()
        yt_file.valid = True
        yt_file.metadata_available = False
        yt_file.video_id = "abc123"
        MockYoutubeFile.return_value = yt_file

        mock_detect.return_value = "pl"
        mock_compare.return_value = True
        mock_titles_to_text.return_value = "plain transcript text"

        with patch("library.youtube_processing.YouTubeTranscriptApi") as MockYTT:
            mock_ytt = MagicMock()
            available = MagicMock()
            available.language_code = "pl"
            mock_ytt.list.return_value = [available]

            fetched = MagicMock()
            fetched.to_raw_data.return_value = [{"text": "hello", "start": 0, "duration": 1}]
            mock_ytt.fetch.return_value = fetched
            MockYTT.return_value = mock_ytt

            process_youtube_url(
                session=mock_session,
                youtube_url="https://www.youtube.com/watch?v=abc",
            )

        assert doc.processing_error_code == StalkerDocumentStatusError.NONE.name
        assert doc.processing_status == StalkerDocumentStatus.NEED_MANUAL_REVIEW.name


# ---------------------------------------------------------------------------
# Test: a video without usable captions is a permanent state, a network block is not
# ---------------------------------------------------------------------------

class TestCaptionsUnavailableVersusBlocked:
    """A video whose only captions are in another language (e.g. Korean) used to end as
    TEMPORARY_ERROR and was retried by every feed_daily run forever."""

    def _run(self, MockWebDocument, MockYoutubeFile, mock_session, fetch_error):
        from library.youtube_processing import process_youtube_url
        from library.models.stalker_document_status import StalkerDocumentStatus

        doc = MagicMock()
        doc.id = 1
        doc.url = "https://www.youtube.com/watch?v=abc"
        doc.processing_status = StalkerDocumentStatus.NEED_TRANSCRIPTION.name
        doc.language = "pl"
        doc.chapter_list = None
        doc.transcript_job_id = None
        doc.transcript_needed = False
        MockWebDocument.get_by_url.return_value = doc

        yt_file = MagicMock()
        yt_file.valid = True
        yt_file.metadata_available = False
        yt_file.video_id = "abc123"
        MockYoutubeFile.return_value = yt_file

        with patch("library.youtube_processing.YouTubeTranscriptApi") as MockYTT:
            korean = MagicMock()
            korean.language_code = "ko"
            MockYTT.return_value.list.return_value = [korean]
            MockYTT.return_value.fetch.side_effect = fetch_error
            process_youtube_url(session=mock_session, youtube_url=doc.url)
        return doc

    @patch("library.youtube_processing.StalkerYoutubeFile")
    @patch("library.youtube_processing.Document")
    def test_no_transcript_in_requested_languages_is_permanent(
        self, MockWebDocument, MockYoutubeFile, mock_session, captions_events
    ):
        from youtube_transcript_api import NoTranscriptFound
        from library.models.stalker_document_status import StalkerDocumentStatus
        from library.models.stalker_document_status_error import StalkerDocumentStatusError

        doc = self._run(MockWebDocument, MockYoutubeFile, mock_session,
                        NoTranscriptFound("abc123", ["en"], MagicMock()))

        assert doc.processing_status == StalkerDocumentStatus.ERROR.name
        assert doc.processing_error_code == StalkerDocumentStatusError.NO_CAPTIONS_AVAILABLE.name
        assert doc.youtube_captions is False
        # YouTube answered, so it is logged as a successful request carrying the reason
        event = captions_events.call_args.kwargs
        assert (event["service"], event["operation"], event["success"], event["error_code"]) == (
            "youtube_captions", "direct", True, "NoTranscriptFound")

    @patch("library.youtube_processing.StalkerYoutubeFile")
    @patch("library.youtube_processing.Document")
    def test_network_block_stays_temporary_and_is_logged(
        self, MockWebDocument, MockYoutubeFile, mock_session, captions_events
    ):
        from library.models.stalker_document_status import StalkerDocumentStatus
        from library.models.stalker_document_status_error import StalkerDocumentStatusError

        doc = self._run(MockWebDocument, MockYoutubeFile, mock_session,
                        ConnectionError("Max retries exceeded with url: /sorry/index?continue=youtube"))

        assert doc.processing_status == StalkerDocumentStatus.TEMPORARY_ERROR.name
        assert doc.processing_error_code == StalkerDocumentStatusError.CAPTIONS_FETCH_ERROR.name
        event = captions_events.call_args.kwargs
        assert (event["success"], event["error_code"]) == (False, "GoogleSorryBlock")

    @patch("library.youtube_processing.StalkerYoutubeFile")
    @patch("library.youtube_processing.Document")
    def test_other_failures_are_logged_under_their_exception_name(
        self, MockWebDocument, MockYoutubeFile, mock_session, captions_events
    ):
        self._run(MockWebDocument, MockYoutubeFile, mock_session, TimeoutError("slow"))
        assert captions_events.call_args.kwargs["error_code"] == "TimeoutError"
        assert captions_events.call_count == 1

    @patch("library.youtube_processing.StalkerYoutubeFile")
    @patch("library.youtube_processing.Document")
    def test_proxy_attempts_are_labelled_as_such(self, MockWebDocument, MockYoutubeFile, mock_session, captions_events):
        from library.youtube_processing import process_youtube_url

        doc = MagicMock(id=1, url="https://www.youtube.com/watch?v=abc", language="pl", chapter_list=None,
                        transcript_job_id=None, transcript_needed=False)
        doc.processing_status = "NEED_TRANSCRIPTION"
        MockWebDocument.get_by_url.return_value = doc
        MockYoutubeFile.return_value = MagicMock(valid=True, metadata_available=False, video_id="abc123")

        with patch("library.youtube_processing.YouTubeTranscriptApi") as MockYTT, \
                patch("library.webshare_ip_auth.get_proxy_credentials", return_value=("u", "p")), \
                patch("youtube_transcript_api.proxies.WebshareProxyConfig"):
            MockYTT.return_value.list.return_value = [MagicMock(language_code="pl")]
            MockYTT.return_value.fetch.side_effect = ConnectionError("boom")
            process_youtube_url(session=mock_session, youtube_url=doc.url, webshare_api_key="key")

        assert captions_events.call_args.kwargs["operation"] == "via_webshare_proxy"


@pytest.fixture(autouse=True)
def correction_rules_without_database(monkeypatch, tmp_path):
    from library import transcript_corrections
    from library import youtube_processing

    monkeypatch.setattr(youtube_processing, "load_config", lambda: {"CACHE_DIR": str(tmp_path)})
    monkeypatch.setattr(transcript_corrections, "load_active_rules", lambda **kwargs: [])
    monkeypatch.setattr(transcript_corrections, "_bump_hit_counts", MagicMock())


@pytest.mark.parametrize("provider", ["captions", "chapters", "language_mismatch", "assemblyai"])
def test_transcript_corrected_at_ingestion(monkeypatch, tmp_path, mock_session, provider):
    from types import SimpleNamespace

    from library import transcript_corrections as rules
    from library import youtube_processing as yt
    from library.db.models import Document
    from library.entity_text import document_ner_text

    pattern = "pi\u0119to Achillesa"
    replacement = "pi\u0119ta Achillesa"
    doc = Document(id=10872, url="https://www.youtube.com/watch?v=abc", document_type="youtube",
                   processing_status="NEED_TRANSCRIPTION", language="pl", byline="channel",
                   transcript_needed=True, transcript_job_id="job", text_md="## " + pattern)
    if provider == "chapters":
        doc.chapter_list = "0:00 Intro\n1:00 Topic"
    monkeypatch.setattr(Document, "get_by_url", lambda session, url: doc)
    monkeypatch.setattr(yt, "StalkerYoutubeFile", lambda **kwargs: SimpleNamespace(
        valid=True, metadata_available=False, video_id="abc", length_seconds=120, length_minutes=2,
        description="", path="unused",
    ))
    ytt = MagicMock()
    ytt.list.return_value = [SimpleNamespace(language_code="pl")]
    ytt.fetch.return_value.to_raw_data.return_value = [{"text": pattern, "start": 0, "duration": 1}]
    if provider == "assemblyai":
        ytt.list.side_effect = yt.TranscriptsDisabled("abc")
        transcript = SimpleNamespace(status="completed", text=pattern, audio_duration=120,
                                     speech_model_used=None, get_paragraphs=lambda: [SimpleNamespace(text=pattern)])
        monkeypatch.setattr(yt.aai.Transcript, "get_by_id", lambda job_id: transcript)
    monkeypatch.setattr(yt, "YouTubeTranscriptApi", lambda: ytt)
    monkeypatch.setattr(yt, "text_language_detect", lambda text: "pl")
    monkeypatch.setattr(yt, "compare_language", lambda *args: provider != "language_mismatch")
    monkeypatch.setattr(yt, "youtube_titles_to_text", lambda text: pattern)
    monkeypatch.setattr(yt, "youtube_titles_split_with_chapters", lambda *args: "## Intro\n" + pattern)
    monkeypatch.setattr(rules, "load_active_rules", lambda **kwargs: [
        rules.TranscriptCorrectionRow(42, "author", "CHANNEL", pattern, replacement),
    ])
    seen_at_commit = []
    mock_session.commit.side_effect = lambda: seen_at_commit.append(doc.text)
    result = yt.process_youtube_url(mock_session, doc.url, cache_dir=str(tmp_path))
    assert replacement in result.text and pattern not in result.text
    assert result.text_md == "## " + replacement
    assert replacement in document_ner_text(result)
    assert pattern not in document_ner_text(result)
    assert replacement in seen_at_commit[-1]
    assert pattern in result.text_raw or "Achillesa" in result.text_raw
    # One correction pass per canonical field, never a second analysis-time pass.
    assert rules._bump_hit_counts.call_count == 2
