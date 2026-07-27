"""NAS worker for feed and content-group suggestion jobs."""

import argparse
import datetime as dt
import logging
import os
import time
from zoneinfo import ZoneInfo
from sqlalchemy import text, select
from library.db.engine import get_session
from library.db.models import Job
from library.feed_monitor_service import run_check
from library.job_queue import claim, finish, heartbeat, recover_stale, enqueue

logger = logging.getLogger("lenie.worker")
logging.basicConfig(level=logging.INFO)
LOCK_KEY = 918273645
HEARTBEAT_PATH = "/tmp/lenie-worker-heartbeat"


def execute(session, job: Job) -> dict:
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
    raise ValueError("unsupported job")


def scheduler(session, now: dt.datetime) -> None:
    local = now.astimezone(ZoneInfo(os.getenv("FEED_TIMEZONE", "Europe/Warsaw")))
    target = os.getenv("FEED_SCHEDULE_TIME", "04:00")
    hour, minute = map(int, target.split(":", 1))
    if (local.hour, local.minute) >= (hour, minute):
        enqueue(session, "feed_daily", idempotency_key=f"feed_daily:{local.date().isoformat()}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--healthcheck", action="store_true")
    args = parser.parse_args()
    session = get_session()
    if args.healthcheck:
        session.execute(text("SELECT 1"))
        try:
            age = time.time() - os.path.getmtime(HEARTBEAT_PATH)
            if age > float(os.getenv("WORKER_HEALTH_MAX_AGE_SECONDS", "30")):
                raise RuntimeError("worker heartbeat is stale")
        except FileNotFoundError as exc:
            raise RuntimeError("worker heartbeat is missing") from exc
        session.close()
        return 0
    if session.execute(select(text("pg_try_advisory_lock(:key)")).params(key=LOCK_KEY)).scalar() is not True:
        logger.error("another worker owns the coordinator lock")
        return 1
    while True:
        with open(HEARTBEAT_PATH, "a", encoding="utf-8"):
            os.utime(HEARTBEAT_PATH, None)
        recover_stale(session)
        scheduler(session, dt.datetime.now(dt.timezone.utc))
        job = claim(session)
        if job is None:
            time.sleep(5)
            continue
        started = time.monotonic()
        logger.info("job start id=%s type=%s attempt=%s", job.id, job.type, job.attempt)
        try:
            if job.status == "cancel_requested":
                finish(session, job, "cancelled")
                continue
            result = execute(session, job)
            finish(session, job, "done", result=result)
        except Exception as exc:
            logger.exception("job failed id=%s", job.id)
            if job.attempt < job.max_attempts:
                from library.job_queue import retry

                retry(session, job)
            else:
                finish(session, job, "failed", error=str(exc)[:2000])
        logger.info("job end id=%s elapsed=%.2fs", job.id, time.monotonic() - started)


if __name__ == "__main__":
    raise SystemExit(main())
