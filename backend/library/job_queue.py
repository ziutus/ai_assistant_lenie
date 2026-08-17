"""Small PostgreSQL queue implementation using row locks, not an in-process queue."""

import datetime as dt
import uuid
from sqlalchemy import select, update
from library.db.models import Job

JOB_TYPES = {
    "feed_check",
    "feed_check_all",
    "feed_auto_import",
    "feed_daily",
    "content_group_suggest",
    "document_prepare",
    "entity_enrichment",
    "legacy_aws_pull",
    "obsidian_reimport",
}


def enqueue(
    session,
    job_type: str,
    parameters: dict | None = None,
    *,
    idempotency_key: str | None = None,
    user_id: int | None = None,
) -> Job:
    if job_type not in JOB_TYPES:
        raise ValueError("unsupported job type")
    if idempotency_key:
        existing = session.scalars(select(Job).where(Job.idempotency_key == idempotency_key)).one_or_none()
        if existing:
            return existing
    job = Job(
        id=uuid.uuid4().hex,
        type=job_type,
        parameters=parameters or {},
        initiated_by_user_id=user_id,
        idempotency_key=idempotency_key,
    )
    session.add(job)
    session.commit()
    return job


def claim(session, allowed_types: set[str] | list[str] | tuple[str, ...]) -> Job | None:
    allowed_types = set(allowed_types or ())
    if not allowed_types:
        raise ValueError("allowed_types must not be empty")
    unsupported = allowed_types - JOB_TYPES
    if unsupported:
        raise ValueError(f"unsupported job types: {sorted(unsupported)}")
    row = session.execute(
        select(Job)
        .where(
            Job.status == "queued",
            Job.type.in_(allowed_types),
            Job.available_at <= dt.datetime.now(dt.timezone.utc),
        )
        .order_by(Job.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    ).scalar_one_or_none()
    if row is None:
        session.rollback()
        return None
    now = dt.datetime.now(dt.timezone.utc)
    row.status, row.attempt, row.started_at, row.heartbeat_at = "running", row.attempt + 1, now, now
    session.commit()
    return row


def heartbeat(session, job_id: str, progress: dict | None = None) -> None:
    values = {"heartbeat_at": dt.datetime.now(dt.timezone.utc)}
    if progress is not None:
        values["progress"] = progress
    session.execute(
        update(Job).where(Job.id == job_id, Job.status.in_(["running", "cancel_requested"])).values(**values)
    )
    session.commit()


def finish(session, job: Job, status: str, *, result=None, error=None) -> None:
    if status not in {"done", "failed", "cancelled"}:
        raise ValueError("invalid final job status")
    job.status, job.result, job.error, job.finished_at = status, result, error, dt.datetime.now(dt.timezone.utc)
    session.commit()


def retry(session, job: Job) -> Job:
    if job.status != "failed" or job.attempt >= job.max_attempts:
        raise RuntimeError("job cannot be retried")
    job.status, job.error, job.result, job.progress, job.available_at = (
        "queued",
        None,
        None,
        None,
        dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=(30, 120, 600)[min(job.attempt - 1, 2)]),
    )
    job.started_at = job.heartbeat_at = job.finished_at = None
    session.commit()
    return job


def cancel(session, job: Job) -> Job:
    if job.status == "queued":
        job.status = "cancelled"
    elif job.status == "running":
        job.status = "cancel_requested"
    else:
        raise RuntimeError("job cannot be cancelled")
    session.commit()
    return job


def recover_stale(session, stale_after: int = 120) -> int:
    threshold = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=stale_after)
    rows = session.scalars(
        select(Job).where(Job.heartbeat_at < threshold, Job.status.in_(["running", "cancel_requested"]))
    ).all()
    for job in rows:
        if job.status == "cancel_requested":
            job.status = "cancelled"
        elif job.attempt < job.max_attempts:
            job.status, job.available_at = "queued", dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=30)
        else:
            job.status, job.error, job.finished_at = (
                "failed",
                "worker heartbeat expired",
                dt.datetime.now(dt.timezone.utc),
            )
    session.commit()
    return len(rows)
