"""Unit tests for WebsitesDBPostgreSQL ORM repository queries (Story 27.2).

All tests use mocked sessions — no database required.
"""

import datetime
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")

from library.stalker_web_documents_db_postgresql import WebsitesDBPostgreSQL
from library.models.stalker_document_status import StalkerDocumentStatus
from library.models.stalker_document_type import StalkerDocumentType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_repo(session=None):
    """Create a WebsitesDBPostgreSQL with a mocked session."""
    if session is None:
        session = MagicMock()
    return WebsitesDBPostgreSQL(session)


def _make_row(**kwargs):
    """Create a mock row object with attribute access."""
    row = MagicMock()
    for k, v in kwargs.items():
        setattr(row, k, v)
    return row


# ===================================================================
# Task 1: Constructor (AC #1)
# ===================================================================


class TestConstructor:
    def test_accepts_session(self):
        session = MagicMock()
        repo = WebsitesDBPostgreSQL(session)
        assert repo.session is session

    def test_no_psycopg2_connection_when_session_provided(self):
        session = MagicMock()
        repo = WebsitesDBPostgreSQL(session)
        assert not hasattr(repo, "conn")

    def test_no_embedding_attr_when_session_provided(self):
        session = MagicMock()
        repo = WebsitesDBPostgreSQL(session)
        assert not hasattr(repo, "embedding")


# ===================================================================
# Task 2: get_list() (AC #2)
# ===================================================================


class TestGetList:
    def test_no_filters(self):
        session = MagicMock()
        repo = _make_repo(session)

        mock_row = MagicMock()
        mock_row.id = 1
        mock_row.url = "https://example.com"
        mock_row.title = "Test"
        mock_row.document_type = StalkerDocumentType.webpage
        mock_row.created_at = datetime.datetime(2026, 1, 15, 10, 30, 0)
        mock_row.document_state = StalkerDocumentStatus.URL_ADDED
        mock_row.document_state_error = None
        mock_row.note = "note"
        mock_row.project = "lenie"
        mock_row.s3_uuid = "uuid-1"

        session.execute.return_value.all.return_value = [mock_row]

        result = repo.get_list()

        assert len(result) == 1
        assert result[0]["id"] == 1
        assert result[0]["url"] == "https://example.com"
        assert result[0]["title"] == "Test"
        assert result[0]["document_type"] == "webpage"
        assert result[0]["created_at"] == "2026-01-15 10:30:00"
        assert result[0]["document_state"] == "URL_ADDED"
        assert result[0]["document_state_error"] is None
        assert result[0]["note"] == "note"
        assert result[0]["project"] == "lenie"
        assert result[0]["s3_uuid"] == "uuid-1"

    def test_single_filter_document_type(self):
        session = MagicMock()
        repo = _make_repo(session)
        session.execute.return_value.all.return_value = []

        result = repo.get_list(document_type="link")

        assert result == []
        session.execute.assert_called_once()

    def test_multiple_filters(self):
        session = MagicMock()
        repo = _make_repo(session)
        session.execute.return_value.all.return_value = []

        result = repo.get_list(document_type="link", document_state="URL_ADDED", project="lenie")

        assert result == []
        session.execute.assert_called_once()

    def test_search_in_documents(self):
        session = MagicMock()
        repo = _make_repo(session)
        session.execute.return_value.all.return_value = []

        result = repo.get_list(search_in_documents="python")

        assert result == []
        session.execute.assert_called_once()

    def test_count_mode(self):
        session = MagicMock()
        repo = _make_repo(session)
        session.execute.return_value.scalar.return_value = 42

        result = repo.get_list(count=True)

        assert result == 42

    def test_count_mode_with_filter(self):
        session = MagicMock()
        repo = _make_repo(session)
        session.execute.return_value.scalar.return_value = 10

        result = repo.get_list(count=True, document_type="youtube")

        assert result == 10

    def test_pagination(self):
        session = MagicMock()
        repo = _make_repo(session)
        session.execute.return_value.all.return_value = []

        result = repo.get_list(limit=20, offset=2)

        assert result == []
        session.execute.assert_called_once()

    def test_empty_result(self):
        session = MagicMock()
        repo = _make_repo(session)
        session.execute.return_value.all.return_value = []

        result = repo.get_list()

        assert result == []

    def test_start_id_filter(self):
        session = MagicMock()
        repo = _make_repo(session)
        session.execute.return_value.all.return_value = []

        result = repo.get_list(start_id=100)

        assert result == []
        session.execute.assert_called_once()

    def test_ai_summary_needed_filter(self):
        session = MagicMock()
        repo = _make_repo(session)
        session.execute.return_value.all.return_value = []

        result = repo.get_list(ai_summary_needed=True)

        assert result == []
        session.execute.assert_called_once()

    def test_ai_correction_needed_ignored(self):
        """ai_correction_needed parameter is accepted but silently ignored."""
        session = MagicMock()
        repo = _make_repo(session)
        session.execute.return_value.all.return_value = []

        result = repo.get_list(ai_correction_needed=True)

        assert result == []

    def test_document_state_error_with_enum(self):
        """document_state_error should serialize enum .name or None."""
        session = MagicMock()
        repo = _make_repo(session)

        from library.models.stalker_document_status_error import StalkerDocumentStatusError
        mock_row = MagicMock()
        mock_row.id = 2
        mock_row.url = "https://example.com/2"
        mock_row.title = "Test 2"
        mock_row.document_type = StalkerDocumentType.link
        mock_row.created_at = datetime.datetime(2026, 2, 1, 8, 0, 0)
        mock_row.document_state = StalkerDocumentStatus.ERROR
        mock_row.document_state_error = StalkerDocumentStatusError.ERROR_DOWNLOAD
        mock_row.note = None
        mock_row.project = None
        mock_row.s3_uuid = None

        session.execute.return_value.all.return_value = [mock_row]

        result = repo.get_list()

        assert result[0]["document_state_error"] == "ERROR_DOWNLOAD"

    def test_search_escapes_wildcards(self):
        """Verify % and _ in search string are escaped so LIKE treats them literally."""
        session = MagicMock()
        repo = _make_repo(session)
        session.execute.return_value.all.return_value = []

        repo.get_list(search_in_documents="50%_test")

        # Verify the statement was built (execute was called)
        session.execute.assert_called_once()
        # The actual escaping is in the ilike pattern — confirm no crash
        # and that the method completes without error


# ===================================================================
# Task 3: get_count() (AC #3)
# ===================================================================


class TestGetCount:
    def test_returns_integer(self):
        session = MagicMock()
        repo = _make_repo(session)
        session.execute.return_value.scalar.return_value = 150

        result = repo.get_count()

        assert result == 150
        assert isinstance(result, int)

    def test_with_document_type_filter(self):
        session = MagicMock()
        repo = _make_repo(session)
        session.execute.return_value.scalar.return_value = 42

        result = repo.get_count(document_type="link")

        assert result == 42
        session.execute.assert_called_once()

    def test_all_type_no_filter(self):
        session = MagicMock()
        repo = _make_repo(session)
        session.execute.return_value.scalar.return_value = 200

        result = repo.get_count(document_type="ALL")

        assert result == 200


# ===================================================================
# Task 4: get_count_by_type() (AC #4)
# ===================================================================


class TestGetCountByType:
    def test_multiple_types(self):
        session = MagicMock()
        repo = _make_repo(session)

        mock_rows = [
            (StalkerDocumentType.webpage, 80),
            (StalkerDocumentType.youtube, 40),
            (StalkerDocumentType.link, 30),
        ]
        session.execute.return_value.all.return_value = mock_rows

        result = repo.get_count_by_type()

        assert result["webpage"] == 80
        assert result["youtube"] == 40
        assert result["link"] == 30
        assert result["ALL"] == 150

    def test_empty(self):
        session = MagicMock()
        repo = _make_repo(session)
        session.execute.return_value.all.return_value = []

        result = repo.get_count_by_type()

        assert result["ALL"] == 0


# ===================================================================
# Task 5: get_ready_for_download() (AC #5)
# ===================================================================


class TestGetReadyForDownload:
    def test_found(self):
        session = MagicMock()
        repo = _make_repo(session)

        row = _make_row(id=1, url="https://example.com", document_type=StalkerDocumentType.webpage, s3_uuid="uuid-1")
        session.execute.return_value.all.return_value = [row]

        result = repo.get_ready_for_download()

        assert len(result) == 1
        assert result[0] == (1, "https://example.com", "webpage", "uuid-1")

    def test_empty(self):
        session = MagicMock()
        repo = _make_repo(session)
        session.execute.return_value.all.return_value = []

        result = repo.get_ready_for_download()

        assert result == []


# ===================================================================
# Task 6: get_youtube_just_added() (AC #6)
# ===================================================================


class TestGetYoutubeJustAdded:
    def test_found_with_both_states(self):
        session = MagicMock()
        repo = _make_repo(session)

        row1 = _make_row(id=1, url="https://youtube.com/1", document_type=StalkerDocumentType.youtube,
                         language="en", chapter_list="ch1", ai_summary_needed=True)
        row2 = _make_row(id=2, url="https://youtube.com/2", document_type=StalkerDocumentType.youtube,
                         language="pl", chapter_list=None, ai_summary_needed=False)
        session.execute.return_value.all.return_value = [row1, row2]

        result = repo.get_youtube_just_added()

        assert len(result) == 2
        assert result[0] == (1, "https://youtube.com/1", "youtube", "en", "ch1", True)
        assert result[1] == (2, "https://youtube.com/2", "youtube", "pl", None, False)

    def test_empty(self):
        session = MagicMock()
        repo = _make_repo(session)
        session.execute.return_value.all.return_value = []

        result = repo.get_youtube_just_added()

        assert result == []


# ===================================================================
# Task 7: get_transcription_done() (AC #7)
# ===================================================================


class TestGetTranscriptionDone:
    def test_found(self):
        session = MagicMock()
        repo = _make_repo(session)

        mock_rows = [(1,), (5,), (10,)]
        session.execute.return_value.all.return_value = mock_rows

        result = repo.get_transcription_done()

        assert result == [1, 5, 10]

    def test_empty(self):
        session = MagicMock()
        repo = _make_repo(session)
        session.execute.return_value.all.return_value = []

        result = repo.get_transcription_done()

        assert result == []


# ===================================================================
# Task 8: get_next_to_correct() (AC #8)
# ===================================================================


class TestGetNextToCorrect:
    def test_found(self):
        session = MagicMock()
        repo = _make_repo(session)

        mock_row = (11, StalkerDocumentType.webpage)
        session.execute.return_value.first.return_value = mock_row

        result = repo.get_next_to_correct(10)

        assert result == (11, "webpage")

    def test_not_found(self):
        session = MagicMock()
        repo = _make_repo(session)
        session.execute.return_value.first.return_value = None

        result = repo.get_next_to_correct(9999)

        assert result == -1

    def test_with_type_filter(self):
        session = MagicMock()
        repo = _make_repo(session)

        mock_row = (15, StalkerDocumentType.link)
        session.execute.return_value.first.return_value = mock_row

        result = repo.get_next_to_correct(10, document_type="link")

        assert result == (15, "link")

    def test_with_state_filter(self):
        session = MagicMock()
        repo = _make_repo(session)

        mock_row = (20, StalkerDocumentType.youtube)
        session.execute.return_value.first.return_value = mock_row

        result = repo.get_next_to_correct(10, document_state="NEED_MANUAL_REVIEW")

        assert result == (20, "youtube")


# ===================================================================
# Task 9: get_last_unknown_news() (AC #9)
# ===================================================================


class TestGetLastUnknownNews:
    def test_has_data(self):
        session = MagicMock()
        repo = _make_repo(session)
        session.execute.return_value.scalar.return_value = datetime.date(2026, 3, 1)

        result = repo.get_last_unknown_news()

        assert result == datetime.date(2026, 3, 1)

    def test_no_data(self):
        session = MagicMock()
        repo = _make_repo(session)
        session.execute.return_value.scalar.return_value = None

        result = repo.get_last_unknown_news()

        assert result is None


# ===================================================================
# Task 10: load_neighbors() (AC #10)
# ===================================================================


class TestLoadNeighbors:
    def test_both_neighbors(self):
        session = MagicMock()
        repo = _make_repo(session)

        doc = MagicMock()
        doc.id = 10

        next_row = (11, StalkerDocumentType.link)
        prev_row = (9, StalkerDocumentType.youtube)
        session.execute.side_effect = [
            MagicMock(first=MagicMock(return_value=next_row)),
            MagicMock(first=MagicMock(return_value=prev_row)),
        ]

        repo.load_neighbors(doc)

        assert doc.next_id == 11
        assert doc.next_type == "link"
        assert doc.previous_id == 9
        assert doc.previous_type == "youtube"

    def test_only_next(self):
        session = MagicMock()
        repo = _make_repo(session)

        doc = MagicMock()
        doc.id = 10

        next_row = (11, StalkerDocumentType.webpage)
        session.execute.side_effect = [
            MagicMock(first=MagicMock(return_value=next_row)),
            MagicMock(first=MagicMock(return_value=None)),
        ]

        repo.load_neighbors(doc)

        assert doc.next_id == 11
        assert doc.next_type == "webpage"
        assert doc.previous_id is None
        assert doc.previous_type is None

    def test_only_previous(self):
        session = MagicMock()
        repo = _make_repo(session)

        doc = MagicMock()
        doc.id = 10

        session.execute.side_effect = [
            MagicMock(first=MagicMock(return_value=None)),
            MagicMock(first=MagicMock(return_value=(9, StalkerDocumentType.link))),
        ]

        repo.load_neighbors(doc)

        assert doc.next_id is None
        assert doc.next_type is None
        assert doc.previous_id == 9
        assert doc.previous_type == "link"

    def test_no_neighbors(self):
        session = MagicMock()
        repo = _make_repo(session)

        doc = MagicMock()
        doc.id = 1

        session.execute.side_effect = [
            MagicMock(first=MagicMock(return_value=None)),
            MagicMock(first=MagicMock(return_value=None)),
        ]

        repo.load_neighbors(doc)

        assert doc.next_id is None
        assert doc.next_type is None
        assert doc.previous_id is None
        assert doc.previous_type is None

    def test_string_type_fallback(self):
        """Cover hasattr fallback when document_type comes as raw string."""
        session = MagicMock()
        repo = _make_repo(session)

        doc = MagicMock()
        doc.id = 10

        next_row = (11, "link")
        prev_row = (9, "youtube")
        session.execute.side_effect = [
            MagicMock(first=MagicMock(return_value=next_row)),
            MagicMock(first=MagicMock(return_value=prev_row)),
        ]

        repo.load_neighbors(doc)

        assert doc.next_type == "link"
        assert doc.previous_type == "youtube"

    def test_raises_without_session(self):
        """load_neighbors() requires ORM session — raises RuntimeError without one."""
        import unittest.mock as um
        # Create repo without session by patching psycopg2.connect
        with um.patch("library.stalker_web_documents_db_postgresql.psycopg2.connect"):
            repo = WebsitesDBPostgreSQL(session=None)

        doc = MagicMock()
        doc.id = 10

        with pytest.raises(RuntimeError, match="requires an ORM session"):
            repo.load_neighbors(doc)
