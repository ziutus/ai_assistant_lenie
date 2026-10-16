"""run_caption_fetch(): sequential caption download for auto-imported feed videos."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("youtube_transcript_api")

from library import feed_monitor_service as service  # noqa: E402
from library import youtube_processing  # noqa: E402

OK, TEMP = "NEED_MANUAL_REVIEW", "TEMPORARY_ERROR"


def _docs(count):
    return [
        SimpleNamespace(id=i, url=f"https://youtu.be/{i}", language="pl", chapter_list=None, note=None,
                        discovery_source_name="feed")
        for i in range(1, count + 1)
    ]


def _setup(monkeypatch, docs, outcomes):
    """outcomes: one entry per process_youtube_url call (a retry is a separate call)."""
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


def _run(session, **kwargs):
    return service.run_caption_fetch(session=session, delay_seconds=0, retry_delay_seconds=0, **kwargs)


def test_fetches_documents_in_order_and_counts_remaining(monkeypatch):
    session, calls = _setup(monkeypatch, _docs(5), [OK] * 3)
    result = _run(session, limit=3)
    assert calls == ["https://youtu.be/1", "https://youtu.be/2", "https://youtu.be/3"]
    assert result == {"fetched": 3, "failed": 0, "retried": 0, "recovered": 0, "remaining": 2,
                      "stopped_early": False, "errors": []}


def test_temporary_error_is_retried_once_and_can_recover(monkeypatch):
    session, calls = _setup(monkeypatch, _docs(1), [TEMP, OK])
    result = _run(session, limit=5)
    assert len(calls) == 2 and calls[0] == calls[1]
    assert (result["fetched"], result["failed"], result["retried"], result["recovered"]) == (1, 0, 1, 1)


def test_retry_failing_again_counts_one_failure_not_two(monkeypatch):
    session, calls = _setup(monkeypatch, _docs(1), [TEMP, TEMP])
    result = _run(session, limit=5)
    assert len(calls) == 2  # exactly one retry
    assert (result["fetched"], result["failed"], result["retried"], result["recovered"]) == (0, 1, 1, 0)


def test_permanent_no_captions_is_not_retried(monkeypatch):
    session, calls = _setup(monkeypatch, _docs(1), ["ERROR"])
    result = _run(session, limit=5)
    assert len(calls) == 1 and result["retried"] == 0


def test_stops_after_consecutive_failures(monkeypatch):
    # doc1 ok; docs 2-4 fail even after their retry -> three failures in a row, docs 5-8 left over
    outcomes = [OK, TEMP, TEMP, TEMP, TEMP, TEMP, TEMP]
    session, calls = _setup(monkeypatch, _docs(8), outcomes)
    result = _run(session, limit=8)
    assert len(calls) == 7
    assert (result["fetched"], result["failed"], result["stopped_early"], result["remaining"]) == (1, 3, True, 4)


def test_exception_is_recorded_and_not_retried(monkeypatch):
    session, calls = _setup(monkeypatch, _docs(1), [RuntimeError("db gone")])
    result = _run(session, limit=5)
    assert len(calls) == 1 and result["failed"] == 1
    assert result["errors"][0]["error"] == "db gone"
    session.rollback.assert_called_once()


def test_success_resets_failure_streak(monkeypatch):
    # fail, fail, ok, fail, fail: never three in a row, so the run is not stopped
    outcomes = [TEMP, TEMP, TEMP, TEMP, OK, TEMP, TEMP, TEMP, TEMP]
    session, calls = _setup(monkeypatch, _docs(5), outcomes)
    result = _run(session, limit=5)
    assert len(calls) == 9 and result["stopped_early"] is False
    assert (result["fetched"], result["failed"]) == (1, 4)
