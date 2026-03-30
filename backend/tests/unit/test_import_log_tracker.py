"""Unit tests for ImportLog model and ImportLogTracker context manager."""

from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest

sa = pytest.importorskip("sqlalchemy")

from library.db.models import ImportLog
from library.import_log_tracker import ImportLogTracker


# ---------------------------------------------------------------------------
# ImportLog model tests
# ---------------------------------------------------------------------------


class TestImportLogModel:
    def test_instantiation_with_defaults(self):
        log = ImportLog(script_name="test_script")
        assert log.script_name == "test_script"
        assert log.status is None  # server_default applies at DB level
        assert log.finished_at is None
        assert log.error_message is None
        assert log.notes is None

    def test_instantiation_with_all_fields(self):
        now = datetime(2026, 3, 29, 12, 0, 0)
        log = ImportLog(
            script_name="dynamodb_sync",
            started_at=now,
            finished_at=now,
            status="success",
            since_date=date(2026, 3, 1),
            until_date=date(2026, 3, 29),
            items_found=100,
            items_added=50,
            items_skipped=45,
            items_error=5,
            parameters={"since": "2026-03-01"},
            error_message=None,
            notes="Test run",
        )
        assert log.script_name == "dynamodb_sync"
        assert log.items_found == 100
        assert log.items_added == 50
        assert log.items_skipped == 45
        assert log.items_error == 5
        assert log.parameters == {"since": "2026-03-01"}
        assert log.since_date == date(2026, 3, 1)
        assert log.until_date == date(2026, 3, 29)
        assert log.notes == "Test run"

    def test_repr(self):
        log = ImportLog(id=1, script_name="test", status="success", started_at=datetime(2026, 3, 29))
        r = repr(log)
        assert "ImportLog" in r
        assert "test" in r
        assert "success" in r


# ---------------------------------------------------------------------------
# ImportLogTracker context manager tests
# ---------------------------------------------------------------------------


def _mock_get_session():
    session = MagicMock()
    session.add = MagicMock()
    session.flush = MagicMock()
    session.commit = MagicMock()
    session.rollback = MagicMock()
    session.close = MagicMock()
    return session


class TestImportLogTracker:
    @patch("library.import_log_tracker.get_session")
    def test_success_path(self, mock_get_session):
        session = _mock_get_session()
        mock_get_session.return_value = session

        with ImportLogTracker("test_script", {"key": "val"}) as tracker:
            tracker.set_counts(found=10, added=5, skipped=3, error=2)
            tracker.set_dates(since_date=date(2026, 3, 1))

        assert tracker.log.script_name == "test_script"
        assert tracker.log.status == "success"
        assert tracker.log.finished_at is not None
        assert tracker.log.items_found == 10
        assert tracker.log.items_added == 5
        assert tracker.log.items_skipped == 3
        assert tracker.log.items_error == 2
        assert tracker.log.since_date == date(2026, 3, 1)
        assert tracker.log.parameters == {"key": "val"}
        assert tracker.log.error_message is None

        session.add.assert_called_once_with(tracker.log)
        session.flush.assert_called_once()
        session.commit.assert_called_once()
        session.close.assert_called_once()

    @patch("library.import_log_tracker.get_session")
    def test_error_path(self, mock_get_session):
        session = _mock_get_session()
        mock_get_session.return_value = session

        with pytest.raises(ValueError, match="test error"):
            with ImportLogTracker("failing_script") as tracker:
                tracker.set_counts(found=5, added=2)
                raise ValueError("test error")

        assert tracker.log.status == "error"
        assert tracker.log.error_message == "test error"
        assert tracker.log.finished_at is not None
        assert tracker.log.items_found == 5
        assert tracker.log.items_added == 2
        session.commit.assert_called_once()
        session.close.assert_called_once()

    @patch("library.import_log_tracker.get_session")
    def test_set_counts_updates_correctly(self, mock_get_session):
        session = _mock_get_session()
        mock_get_session.return_value = session

        with ImportLogTracker("script") as tracker:
            tracker.set_counts(found=100, added=90, skipped=8, error=2)
            # Update counts again (like incremental updates)
            tracker.set_counts(found=200, added=180, skipped=15, error=5)

        assert tracker.log.items_found == 200
        assert tracker.log.items_added == 180
        assert tracker.log.items_skipped == 15
        assert tracker.log.items_error == 5

    @patch("library.import_log_tracker.get_session")
    def test_log_persists_even_on_exception(self, mock_get_session):
        session = _mock_get_session()
        mock_get_session.return_value = session

        with pytest.raises(RuntimeError):
            with ImportLogTracker("crash_script") as tracker:
                raise RuntimeError("crash")

        # commit was called (log persisted) even though exception propagated
        session.commit.assert_called_once()
        assert tracker.log.status == "error"
        session.close.assert_called_once()

    @patch("library.import_log_tracker.get_session")
    def test_commit_failure_triggers_rollback(self, mock_get_session):
        session = _mock_get_session()
        session.commit.side_effect = Exception("DB error")
        mock_get_session.return_value = session

        with ImportLogTracker("script") as _tracker:
            pass

        session.rollback.assert_called_once()
        session.close.assert_called_once()

    @patch("library.import_log_tracker.get_session")
    def test_default_parameters_is_empty_dict(self, mock_get_session):
        session = _mock_get_session()
        mock_get_session.return_value = session

        with ImportLogTracker("script") as tracker:
            pass

        assert tracker.log.parameters == {}

    @patch("library.import_log_tracker.get_session")
    def test_add_note(self, mock_get_session):
        session = _mock_get_session()
        mock_get_session.return_value = session

        with ImportLogTracker("script") as tracker:
            tracker.add_note("First note")
            tracker.add_note("Second note")

        assert tracker.log.notes == "First note\nSecond note"

    @patch("library.import_log_tracker.get_session")
    def test_set_dates(self, mock_get_session):
        session = _mock_get_session()
        mock_get_session.return_value = session

        with ImportLogTracker("script") as tracker:
            tracker.set_dates(
                since_date=date(2026, 3, 1),
                until_date=date(2026, 3, 29),
            )

        assert tracker.log.since_date == date(2026, 3, 1)
        assert tracker.log.until_date == date(2026, 3, 29)
