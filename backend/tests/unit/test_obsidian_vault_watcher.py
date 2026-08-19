"""Unit tests for obsidian_vault_watcher (Story 42.3).

DebouncedReimportHandler's timer/enqueue logic is exercised directly (no
real watchdog Observer, no real filesystem events) by calling its handler
methods with fake watchdog-shaped events and a short debounce, then waiting
for the daemon timer to fire.
"""

import time
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("watchdog")

from library.obsidian_vault_watcher import DebouncedReimportHandler, start_watcher


def _event(src_path, is_directory=False, dest_path=None):
    event = MagicMock()
    event.src_path = src_path
    event.is_directory = is_directory
    event.dest_path = dest_path
    return event


def _wait_for(predicate, timeout=2.0, interval=0.02):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


class TestDebouncedReimportHandler:
    def test_modified_md_file_enqueues_after_debounce(self, tmp_path):
        session = MagicMock()
        session.scalar.return_value = None
        session_factory = MagicMock(return_value=session)
        handler = DebouncedReimportHandler(session_factory, tmp_path, debounce_seconds=0.05)

        note = tmp_path / "02-wiedza/Informatyka/k8s.md"
        note.parent.mkdir(parents=True)
        note.write_text("treść", encoding="utf-8")

        with patch("library.obsidian_vault_watcher.enqueue") as mock_enqueue:
            handler.on_modified(_event(str(note)))
            assert _wait_for(lambda: mock_enqueue.called)

        mock_enqueue.assert_called_once_with(
            session, "obsidian_reimport", {"relative_path": "02-wiedza/Informatyka/k8s.md"}
        )
        session.close.assert_called_once()

    def test_rapid_successive_events_are_coalesced_into_one_enqueue(self, tmp_path):
        session = MagicMock()
        session.scalar.return_value = None
        session_factory = MagicMock(return_value=session)
        handler = DebouncedReimportHandler(session_factory, tmp_path, debounce_seconds=0.1)

        note = tmp_path / "02-wiedza/Informatyka/k8s.md"
        note.parent.mkdir(parents=True)
        note.write_text("treść", encoding="utf-8")

        with patch("library.obsidian_vault_watcher.enqueue") as mock_enqueue:
            for _ in range(5):
                handler.on_modified(_event(str(note)))
                time.sleep(0.02)
            assert _wait_for(lambda: mock_enqueue.called)
            time.sleep(0.15)

        assert mock_enqueue.call_count == 1

    def test_non_markdown_file_is_ignored(self, tmp_path):
        session_factory = MagicMock()
        handler = DebouncedReimportHandler(session_factory, tmp_path, debounce_seconds=0.05)

        other = tmp_path / "02-wiedza/Informatyka/notes.txt"
        other.parent.mkdir(parents=True)
        other.write_text("treść", encoding="utf-8")

        handler.on_modified(_event(str(other)))
        time.sleep(0.15)

        session_factory.assert_not_called()

    def test_directory_event_is_ignored(self, tmp_path):
        session_factory = MagicMock()
        handler = DebouncedReimportHandler(session_factory, tmp_path, debounce_seconds=0.05)

        handler.on_created(_event(str(tmp_path / "02-wiedza/Informatyka"), is_directory=True))
        time.sleep(0.15)

        session_factory.assert_not_called()

    def test_moved_event_uses_destination_path(self, tmp_path):
        session = MagicMock()
        session.scalar.return_value = None
        session_factory = MagicMock(return_value=session)
        handler = DebouncedReimportHandler(session_factory, tmp_path, debounce_seconds=0.05)

        dest = tmp_path / "02-wiedza/Informatyka/renamed.md"
        dest.parent.mkdir(parents=True)
        dest.write_text("treść", encoding="utf-8")

        with patch("library.obsidian_vault_watcher.enqueue") as mock_enqueue:
            handler.on_moved(_event(str(tmp_path / "tmp-name.tmp"), dest_path=str(dest)))
            assert _wait_for(lambda: mock_enqueue.called)

        mock_enqueue.assert_called_once_with(
            session, "obsidian_reimport", {"relative_path": "02-wiedza/Informatyka/renamed.md"}
        )

    def test_skips_enqueue_when_a_job_for_the_note_is_already_active(self, tmp_path):
        session = MagicMock()
        session.scalar.return_value = "existing-job-id"
        session_factory = MagicMock(return_value=session)
        handler = DebouncedReimportHandler(session_factory, tmp_path, debounce_seconds=0.05)

        note = tmp_path / "02-wiedza/Informatyka/k8s.md"
        note.parent.mkdir(parents=True)
        note.write_text("treść", encoding="utf-8")

        with patch("library.obsidian_vault_watcher.enqueue") as mock_enqueue:
            handler.on_modified(_event(str(note)))
            assert _wait_for(lambda: session.scalar.called)
            time.sleep(0.1)

        mock_enqueue.assert_not_called()

    def test_path_outside_vault_is_ignored(self, tmp_path):
        session_factory = MagicMock()
        handler = DebouncedReimportHandler(session_factory, tmp_path, debounce_seconds=0.05)

        elsewhere = tmp_path.parent / "elsewhere.md"

        handler.on_modified(_event(str(elsewhere)))
        time.sleep(0.15)

        session_factory.assert_not_called()


class TestStartWatcher:
    def test_returns_none_when_no_pilot_subfolder_exists(self, tmp_path):
        assert start_watcher(MagicMock(), tmp_path) is None

    def test_starts_observer_when_a_pilot_subfolder_exists(self, tmp_path):
        (tmp_path / "02-wiedza/Informatyka").mkdir(parents=True)

        observer = start_watcher(MagicMock(), tmp_path)
        try:
            assert observer is not None
            assert observer.is_alive()
        finally:
            if observer is not None:
                observer.stop()
                observer.join(timeout=2)
