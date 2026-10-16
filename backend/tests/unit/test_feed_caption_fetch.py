"""run_caption_fetch(): sequential caption download for auto-imported feed videos."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("youtube_transcript_api")

from library import feed_monitor_service as service  # noqa: E402
from library import youtube_processing  # noqa: E402


def _docs(count):
    return [
        SimpleNamespace(id=i, url=f"https://youtu.be/{i}", language="pl", chapter_list=None, note=None,
                        discovery_source_name="feed")
        for i in range(1, count + 1)
    ]


def _setup(monkeypatch, docs, outcomes):
    session = MagicMock()
    session.scalars.return_value.unique.return_value.all.return_value = docs
    session.get.side_effect = lambda model, doc_id: next(d for d in docs if d.id == doc_id)
    calls = []

    def fake_process(session, youtube_url, **kwargs):
        calls.append(youtube_url)
        outcome = outcomes[len(calls) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(processing_status=outcome)

    monkeypatch.setattr(youtube_processing, "process_youtube_url", fake_process)
    monkeypatch.setattr("library.config_loader.load_config", lambda: {"WEBSHARE_API_KEY": "k"})
    return session, calls


def test_fetches_documents_in_order_and_counts_remaining(monkeypatch):
    session, calls = _setup(monkeypatch, _docs(5), ["NEED_MANUAL_REVIEW"] * 3)
    result = service.run_caption_fetch(session=session, limit=3, delay_seconds=0)
    assert calls == ["https://youtu.be/1", "https://youtu.be/2", "https://youtu.be/3"]
    assert result == {"fetched": 3, "failed": 0, "remaining": 2, "stopped_early": False, "errors": []}


def test_stops_after_consecutive_failures(monkeypatch):
    outcomes = ["NEED_MANUAL_REVIEW", "TEMPORARY_ERROR", RuntimeError("blocked"), "TEMPORARY_ERROR"]
    session, calls = _setup(monkeypatch, _docs(8), outcomes)
    result = service.run_caption_fetch(session=session, limit=8, delay_seconds=0)
    assert len(calls) == 4  # 1 ok + 3 failures in a row, the remaining 4 are left for the next run
    assert (result["fetched"], result["failed"], result["stopped_early"], result["remaining"]) == (1, 3, True, 4)
    assert result["errors"][0]["error"] == "blocked"
    session.rollback.assert_called_once()


def test_success_resets_failure_streak(monkeypatch):
    outcomes = ["TEMPORARY_ERROR", "TEMPORARY_ERROR", "NEED_MANUAL_REVIEW", "TEMPORARY_ERROR", "TEMPORARY_ERROR"]
    session, calls = _setup(monkeypatch, _docs(5), outcomes)
    result = service.run_caption_fetch(session=session, limit=5, delay_seconds=0)
    assert len(calls) == 5 and result["stopped_early"] is False
