"""PostgreSQL-backed worker for feed and document jobs."""

import argparse
import datetime as dt
import logging
import os
import time
from zoneinfo import ZoneInfo
from sqlalchemy import text, select
from library.db.engine import get_session
from library.db.models import Job, ScheduledTask
from library.feed_monitor_service import run_check
from library.job_queue import claim, finish, heartbeat, recover_stale, enqueue, retry
from library.job_queue import JOB_TYPES

logger = logging.getLogger("lenie.worker")
logging.basicConfig(level=logging.INFO)
LOCK_KEY = 918273645
HEARTBEAT_PATH = "/tmp/lenie-worker-heartbeat"


def execute(session, job: Job, *, storage=None, work_dir: str = "/app/work") -> dict:
    if job.type == "feed_check":
        return run_check(job.parameters.get("feed_source_id"))
    if job.type == "feed_check_all":
        return run_check()
    if job.type == "feed_auto_import":
        from library.feed_monitor_service import run_auto_import

        return run_auto_import(job.parameters.get("feed_source_id"))
    if job.type == "feed_daily":
        check = run_check()
        heartbeat(session, job.id, {"phase": "check", **check})
        from library.feed_monitor_service import run_auto_import

        return {"check": check, "import": run_auto_import()}
    if job.type == "content_group_suggest":
        from library.content_group_suggestion_service import execute_suggestion_job

        return execute_suggestion_job(session, job)
    if job.type == "document_prepare":
        if storage is None:
            from library.config_loader import load_config
            from library.storage import storage_from_config

            storage = storage_from_config(load_config())
        from library.document_processing_service import execute_document_prepare

        return execute_document_prepare(session, job, storage, work_dir)
    if job.type == "entity_enrichment":
        from library.entity_enrichment_service import execute_entity_enrichment

        return execute_entity_enrichment(session, job)
    if job.type == "obsidian_reimport":
        from library.obsidian_reimport_service import execute_obsidian_reimport

        return execute_obsidian_reimport(session, job)
    if job.type == "tool_candidate_detect":
        from library.tool_candidate_detection_service import execute_tool_candidate_detect

        return execute_tool_candidate_detect(session, job)
    if job.type == "legacy_aws_pull":
        from library.config_loader import load_config
        from library.legacy_aws_pull_service import LegacyAwsPullService
        from library.storage import storage_from_config

        cfg = load_config()
        return LegacyAwsPullService(session, storage or storage_from_config(cfg), cfg).run(job.parameters)
    raise ValueError("unsupported job")


def handle_job_failure(session, job: Job, exc: Exception) -> None:
    """Record a failed attempt before scheduling its retry."""
    error = str(exc)[:2000]
    if job.attempt < job.max_attempts:
        # retry() deliberately accepts only a failed job.  Without this
        # transition a partial bridge error left the job stuck as running.
        finish(session, job, "failed", error=error)
        retry(session, job)
    else:
        finish(session, job, "failed", error=error)


def scheduler(session, now: dt.datetime) -> None:
    for task in session.scalars(select(ScheduledTask)).all():
        if not task.enabled or not _is_due(task, now):
            continue
        if task.id == "feed_daily":
            local = now.astimezone(ZoneInfo(task.timezone))
            enqueue(session, "feed_daily", idempotency_key=f"feed_daily:{local.date().isoformat()}")
        elif task.id == "legacy_aws_pull":
            _schedule_legacy_aws_pull(session, now, task)
        elif task.id == "obsidian_reimport":
            _schedule_obsidian_reimport(session)


def _is_due(task: ScheduledTask, now: dt.datetime) -> bool:
    """Return whether ``now`` falls in one of the task's configured local minutes."""
    try:
        local = now.astimezone(ZoneInfo(task.timezone))
        times = {(int(value.split(":", 1)[0]), int(value.split(":", 1)[1])) for value in task.times}
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"invalid schedule for {task.id}") from exc
    return (local.hour, local.minute) in times


def _schedule_legacy_aws_pull(session, now: dt.datetime, task: ScheduledTask) -> None:
    """Create at most one bridge job for each configured local schedule minute."""
    local = now.astimezone(ZoneInfo(task.timezone)).replace(second=0, microsecond=0)
    active = session.scalar(
        select(Job.id).where(
            Job.type == "legacy_aws_pull",
            Job.status.in_(("queued", "running", "cancel_requested")),
        ).limit(1)
    )
    if active is not None:
        return
    enqueue(
        session,
        "legacy_aws_pull",
        idempotency_key=f"legacy_aws_pull:{local.strftime('%Y-%m-%dT%H:%M%z')}",
    )


def _schedule_obsidian_reimport(session) -> None:
    """Enqueue at most one obsidian_reimport job at a time.

    Unlike _schedule_legacy_aws_pull, dedup is purely "is one already
    active" -- the vault scan can legitimately take longer than the 5-minute
    schedule interval, and the goal is "one run at a time", not "exactly one
    run per scheduled minute".
    """
    active = session.scalar(
        select(Job.id).where(
            Job.type == "obsidian_reimport",
            Job.status.in_(("queued", "running", "cancel_requested")),
        ).limit(1)
    )
    if active is not None:
        return
    enqueue(session, "obsidian_reimport")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--healthcheck", action="store_true")
    parser.add_argument(
        "--types",
        default="feed_check,feed_check_all,feed_auto_import,feed_daily,content_group_suggest,entity_enrichment,obsidian_reimport,tool_candidate_detect",
        help="comma-separated job types handled by this worker",
    )
    parser.add_argument("--scheduler", action="store_true")
    args = parser.parse_args()
    allowed_types = {value.strip() for value in args.types.split(",") if value.strip()}
    unsupported = allowed_types - JOB_TYPES
    if not allowed_types or unsupported:
        parser.error(f"invalid worker types: {sorted(unsupported) or 'empty list'}")
    session = get_session()
    heartbeat_path = os.getenv("WORKER_HEARTBEAT_PATH", HEARTBEAT_PATH)
    if args.healthcheck:
        session.execute(text("SELECT 1"))
        try:
            age = time.time() - os.path.getmtime(heartbeat_path)
            if age > float(os.getenv("WORKER_HEALTH_MAX_AGE_SECONDS", "30")):
                raise RuntimeError("worker heartbeat is stale")
        except FileNotFoundError as exc:
            raise RuntimeError("worker heartbeat is missing") from exc
        session.close()
        return 0
    coordinator = args.scheduler
    if (
        coordinator
        and session.execute(select(text("pg_try_advisory_lock(:key)")).params(key=LOCK_KEY)).scalar() is not True
    ):
        logger.error("another worker owns the coordinator lock")
        return 1
    storage = None
    work_dir = os.getenv("DOCUMENT_WORK_DIR", "/app/work")
    if "document_prepare" in allowed_types:
        from library.config_loader import load_config
        from library.storage import storage_from_config

        cfg = load_config()
        storage = storage_from_config(cfg)
        work_dir = cfg.get("DOCUMENT_WORK_DIR") or work_dir
    while True:
        with open(heartbeat_path, "a", encoding="utf-8"):
            os.utime(heartbeat_path, None)
        if coordinator:
            recover_stale(session)
            scheduler(session, dt.datetime.now(dt.timezone.utc))
        job = claim(session, allowed_types)
        if job is None:
            time.sleep(5)
            continue
        started = time.monotonic()
        logger.info("job start id=%s type=%s attempt=%s", job.id, job.type, job.attempt)
        try:
            if job.status == "cancel_requested":
                finish(session, job, "cancelled")
                continue
            result = execute(session, job, storage=storage, work_dir=work_dir)
            finish(session, job, "done", result=result)
        except Exception as exc:
            from library.document_processing_service import DocumentJobCancelled

            if isinstance(exc, DocumentJobCancelled):
                finish(session, job, "cancelled", error=str(exc))
                continue
            logger.exception("job failed id=%s", job.id)
            handle_job_failure(session, job, exc)
        logger.info("job end id=%s elapsed=%.2fs", job.id, time.monotonic() - started)


if __name__ == "__main__":
    raise SystemExit(main())
