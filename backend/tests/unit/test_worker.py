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


def test_obsidian_reimport_job_is_dispatched_to_service(monkeypatch):
    result = {"scanned": 2, "created": 1, "skipped": 1, "failed": 0}
    execute_obsidian_reimport = MagicMock(return_value=result)
    monkeypatch.setattr(
        "library.obsidian_reimport_service.execute_obsidian_reimport", execute_obsidian_reimport
    )

    session = MagicMock()
    job = MagicMock(type="obsidian_reimport")
    assert worker.execute(session, job) == result
    execute_obsidian_reimport.assert_called_once_with(session, job)


def test_tool_candidate_detect_job_is_dispatched_to_service(monkeypatch):
    result = {"documents_scanned": 1, "candidates_created": 1, "mentions_evaluated": 1, "documents_skipped_empty": 0, "documents_failed": 0}
    execute_tool_candidate_detect = MagicMock(return_value=result)
    monkeypatch.setattr(
        "library.tool_candidate_detection_service.execute_tool_candidate_detect", execute_tool_candidate_detect
    )

    session = MagicMock()
    job = MagicMock(type="tool_candidate_detect")
    assert worker.execute(session, job) == result
    execute_tool_candidate_detect.assert_called_once_with(session, job)


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


def test_disabled_legacy_pull_task_is_not_scheduled(monkeypatch):
    session = MagicMock()
    enqueue = MagicMock()
    session.scalars.return_value.all.return_value = [MagicMock(id="legacy_aws_pull", enabled=False)]
    monkeypatch.setattr(worker, "enqueue", enqueue)

    worker.scheduler(session, dt.datetime(2026, 7, 29, 15, 25, tzinfo=dt.timezone.utc))

    session.scalar.assert_not_called()
    enqueue.assert_not_called()


def test_legacy_pull_scheduler_uses_utc_bucket_and_skips_active_job(monkeypatch):
    session = MagicMock()
    session.scalar.return_value = None
    enqueue = MagicMock()
    monkeypatch.setattr(worker, "enqueue", enqueue)
    task = MagicMock(timezone="Europe/Warsaw")

    worker._schedule_legacy_aws_pull(
        session, dt.datetime(2026, 7, 29, 17, 26, tzinfo=dt.timezone(dt.timedelta(hours=2))), task
    )

    enqueue.assert_called_once_with(session, "legacy_aws_pull", idempotency_key="legacy_aws_pull:2026-07-29T17:26+0200")
    session.scalar.return_value = "already-active"
    worker._schedule_legacy_aws_pull(session, dt.datetime(2026, 7, 29, 15, 30, tzinfo=dt.timezone.utc), task)
    enqueue.assert_called_once()


def test_obsidian_reimport_scheduler_skips_active_job(monkeypatch):
    session = MagicMock()
    enqueue = MagicMock()
    monkeypatch.setattr(worker, "enqueue", enqueue)

    session.scalar.return_value = None
    worker._schedule_obsidian_reimport(session)
    enqueue.assert_called_once_with(session, "obsidian_reimport")

    session.scalar.return_value = "already-active"
    worker._schedule_obsidian_reimport(session)
    enqueue.assert_called_once()


def test_scheduler_dispatches_obsidian_reimport(monkeypatch):
    session = MagicMock()
    task = MagicMock(id="obsidian_reimport", enabled=True, timezone="UTC", times=["12:00"])
    session.scalars.return_value.all.return_value = [task]
    schedule_obsidian = MagicMock()
    monkeypatch.setattr(worker, "_schedule_obsidian_reimport", schedule_obsidian)

    worker.scheduler(session, dt.datetime(2026, 7, 29, 12, 0, tzinfo=dt.timezone.utc))

    schedule_obsidian.assert_called_once_with(session)


def test_scheduler_rejects_invalid_task_time():
    task = MagicMock(id="legacy_aws_pull", timezone="Europe/Warsaw", times=["invalid"])

    try:
        worker._is_due(task, dt.datetime.now(dt.timezone.utc))
    except ValueError as exc:
        assert str(exc) == "invalid schedule for legacy_aws_pull"
    else:
        raise AssertionError("invalid schedule must be rejected")
