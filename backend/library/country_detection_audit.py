"""Best-effort country detection audit, owned by the caller's transaction."""

import logging

from sqlalchemy import select

from library.db.models import CountryDetectionRun, CountryTagDecision

logger = logging.getLogger(__name__)


def record_detection(session, document_id, audit, *, trigger, text_source, analysis_run_id=None,
                     tags_before=None, tags_added=()) -> int | None:
    """Persist a run and its decisions inside a savepoint; never commit the caller's work."""
    try:
        with session.begin_nested():
            llm = audit["llm"]
            run = CountryDetectionRun(
                document_id=document_id, analysis_run_id=analysis_run_id, trigger=trigger, text_source=text_source,
                text_chars=audit["text_chars"], threshold=audit["threshold"], llm_called=llm["called"],
                llm_model=llm["model"], llm_prompt=llm["prompt"], llm_response=llm["response"],
                llm_usage_log_id=llm["usage_log_id"], llm_error=llm["error"],
                tags_before=tags_before, tags_added=list(tags_added),
            )
            session.add(run)
            session.flush()
            for decision in audit["decisions"]:
                session.add(CountryTagDecision(
                    detection_run_id=run.id, country_slug=decision["slug"], country_name=decision["name_pl"],
                    mention_count=decision["mention_count"], decision=decision["decision"],
                    snippets=decision["snippets"],
                ))
            session.flush()
            detection_id = run.id
        return detection_id
    except Exception:
        logger.exception("Failed to record country detection for document %s", document_id)
        return None


def _as_dict(row):
    result = {column.name: getattr(row, column.name) for column in row.__table__.columns}
    result["created_at"] = row.created_at.isoformat() if row.created_at else None
    return result


def list_detections(session, document_id, limit=5) -> list[dict]:
    """Newest runs first, including complete prompts, responses and country decisions."""
    runs = session.scalars(select(CountryDetectionRun).where(
        CountryDetectionRun.document_id == document_id,
    ).order_by(CountryDetectionRun.created_at.desc(), CountryDetectionRun.id.desc()).limit(limit)).all()
    if not runs:
        return []
    decisions = session.scalars(select(CountryTagDecision).where(
        CountryTagDecision.detection_run_id.in_([run.id for run in runs]),
    ).order_by(CountryTagDecision.id)).all()
    grouped = {run.id: [] for run in runs}
    for decision in decisions:
        grouped[decision.detection_run_id].append(_as_dict(decision))
    return [{**_as_dict(run), "decisions": grouped[run.id]} for run in runs]
