from unittest.mock import MagicMock
import datetime as dt

import worker


def test_legacy_aws_pull_job_is_dispatched_to_bridge_service(monkeypatch):
    cfg = MagicMock()
    bridge = MagicMock()
    bridge.run.return_value = {"found": 0}
    monkeypatch.setattr("library.config_loader.load_config", lambda: cfg)
    monkeypatch.setattr("library.storage.storage_from_config", lambda received: MagicMock())
    monkeypatch.setattr("library.legacy_aws_pull_service.LegacyAwsPullService", lambda *args: bridge)

    job = MagicMock(type="legacy_aws_pull", parameters={"since": "2026-07-20T00:00:00Z"})
    assert worker.execute(MagicMock(), job) == {"found": 0}
    bridge.run.assert_called_once_with(job.parameters)


def test_retryable_failure_is_marked_failed_before_retry(monkeypatch):
    session = MagicMock()
    job = MagicMock(attempt=1, max_attempts=3)
    finish = MagicMock()
    retry = MagicMock()
    monkeypatch.setattr(worker, "finish", finish)
    monkeypatch.setattr(worker, "retry", retry)

    worker.handle_job_failure(session, job, RuntimeError("partial import"))

    finish.assert_called_once_with(session, job, "failed", error="partial import")
    retry.assert_called_once_with(session, job)


def test_final_failure_is_not_retried(monkeypatch):
    session = MagicMock()
    job = MagicMock(attempt=3, max_attempts=3)
    finish = MagicMock()
    retry = MagicMock()
    monkeypatch.setattr(worker, "finish", finish)
    monkeypatch.setattr(worker, "retry", retry)

    worker.handle_job_failure(session, job, RuntimeError("final failure"))

    finish.assert_called_once_with(session, job, "failed", error="final failure")
    retry.assert_not_called()


def test_legacy_pull_scheduler_is_disabled_by_default(monkeypatch):
    session = MagicMock()
    enqueue = MagicMock()
    monkeypatch.delenv("AWS_LEGACY_PULL_ENABLED", raising=False)
    monkeypatch.setattr(worker, "enqueue", enqueue)

    worker._schedule_legacy_aws_pull(session, dt.datetime(2026, 7, 29, 15, 25, tzinfo=dt.timezone.utc))

    session.scalar.assert_not_called()
    enqueue.assert_not_called()


def test_legacy_pull_scheduler_uses_utc_bucket_and_skips_active_job(monkeypatch):
    session = MagicMock()
    session.scalar.return_value = None
    enqueue = MagicMock()
    monkeypatch.setenv("AWS_LEGACY_PULL_ENABLED", "true")
    monkeypatch.setenv("AWS_LEGACY_PULL_INTERVAL_MINUTES", "15")
    monkeypatch.setattr(worker, "enqueue", enqueue)

    worker._schedule_legacy_aws_pull(
        session, dt.datetime(2026, 7, 29, 17, 26, tzinfo=dt.timezone(dt.timedelta(hours=2)))
    )

    enqueue.assert_called_once_with(session, "legacy_aws_pull", idempotency_key="legacy_aws_pull:2026-07-29T15:15Z")
    session.scalar.return_value = "already-active"
    worker._schedule_legacy_aws_pull(session, dt.datetime(2026, 7, 29, 15, 30, tzinfo=dt.timezone.utc))
    enqueue.assert_called_once()


def test_legacy_pull_scheduler_rejects_invalid_interval(monkeypatch):
    monkeypatch.setenv("AWS_LEGACY_PULL_ENABLED", "true")
    monkeypatch.setenv("AWS_LEGACY_PULL_INTERVAL_MINUTES", "0")

    try:
        worker._schedule_legacy_aws_pull(MagicMock(), dt.datetime.now(dt.timezone.utc))
    except ValueError as exc:
        assert str(exc) == "AWS_LEGACY_PULL_INTERVAL_MINUTES must be a positive integer"
    else:
        raise AssertionError("invalid interval must be rejected")
