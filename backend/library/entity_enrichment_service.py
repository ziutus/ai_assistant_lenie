"""Background verification of the entities already extracted from a document.

NER itself remains in the request that the editor starts.  The slower work
(geocoding, LLM relevance checks, Wikidata and Overpass) is a durable job, so
closing the editor or a slow external service cannot make the user repeat it.
"""

from __future__ import annotations

import hashlib
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from library.db.models import Document, Job
from library.job_queue import enqueue, heartbeat

ENTITY_ENRICHMENT = "entity_enrichment"
ACTIVE_STATUSES = {"queued", "running", "cancel_requested"}


class EntityEnrichmentCriticalError(RuntimeError):
    """A rollback in a required enrichment stage.

    Place and person resolution are the purpose of an ``entity_enrichment``
    job, so a failed transaction there must never be reported as a successful
    job with a warning.  The worker uses ``requires_manual_intervention`` to
    distinguish a deterministic database/integrity failure from a transient
    dependency failure that may be retried safely.
    """

    def __init__(self, stage_errors: dict[str, Exception]):
        self.stage_errors = stage_errors
        self.requires_manual_intervention = any(
            isinstance(error, IntegrityError) for error in stage_errors.values()
        )
        stages = ", ".join(stage_errors)
        details = "; ".join(f"{stage}: {error}" for stage, error in stage_errors.items())
        super().__init__(f"critical entity-enrichment stage failure ({stages}): {details}")

    def job_result(self, document_id: int) -> dict:
        return {
            "document_id": document_id,
            "failed_stages": list(self.stage_errors),
            "failure_kind": "integrity" if self.requires_manual_intervention else "transient",
            "action": "manual_intervention" if self.requires_manual_intervention else "retry",
        }


def _text_digest(document: Document) -> str:
    text = document.text_md or document.text or ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def ensure_entity_enrichment_job(session: Session, document: Document, user_id: int | None = None) -> Job:
    """Return the active enrichment job, or queue one for this NER refresh."""
    existing = session.scalars(
        select(Job)
        .where(
            Job.type == ENTITY_ENRICHMENT,
            Job.status.in_(ACTIVE_STATUSES),
            Job.parameters["document_id"].as_integer() == document.id,
        )
        .order_by(Job.created_at.desc())
        .limit(1)
    ).first()
    if existing is not None:
        return existing
    # A completed job must not suppress verification after a later NER refresh:
    # refreshing replaces the entity rows and their links to cached results.
    key = f"{ENTITY_ENRICHMENT}:{document.id}:{_text_digest(document)}:{uuid.uuid4().hex}"
    return enqueue(
        session,
        ENTITY_ENRICHMENT,
        {"document_id": document.id, "text_digest": _text_digest(document)},
        idempotency_key=key,
        user_id=user_id,
    )


def job_view(job: Job) -> dict:
    return {
        "id": job.id,
        "status": job.status,
        "progress": job.progress,
        "result": job.result,
        "error": job.error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


def execute_entity_enrichment(session: Session, job: Job) -> dict:
    """Run independent place/person verification in parallel, then pipelines."""
    document_id = int(job.parameters["document_id"])
    doc = session.get(Document, document_id)
    if doc is None:
        raise RuntimeError(f"document {document_id} no longer exists")
    if job.parameters.get("text_digest") != _text_digest(doc):
        return {"document_id": document_id, "skipped": "document text changed"}

    text = doc.text_md or doc.text or ""
    result: dict = {"document_id": document_id, "place_tags": [], "persons_linked": 0, "pipelines": [], "warnings": []}
    progress_lock = Lock()
    stages: dict[str, dict] = {}

    def report(progress_session: Session, phase: str, label: str, current: int, total: int) -> None:
        # The two parallel stages have separate SQLAlchemy sessions.  Serialize
        # their progress writes so neither overwrites the other stage's counter.
        with progress_lock:
            stages[phase] = {"label": label, "current": current, "total": total}
            heartbeat(progress_session, job.id, {"document_id": document_id, "stages": dict(stages)})

    def verify_places() -> tuple[list[str], Exception | None]:
        from library.db.engine import get_session
        from library.llm_usage.context import llm_usage_context
        from library.place_verification import verify_document_places

        stage_session = get_session()
        try:
            stage_doc = stage_session.get(Document, document_id)
            report(stage_session, "verify_places", "Miejsca", 0, 0)
            with llm_usage_context(document_id=document_id):
                summary = verify_document_places(
                    stage_session, stage_doc, text,
                    progress_callback=lambda current, total: report(
                        stage_session, "verify_places", "Miejsca", current, total,
                    ),
                )
            stage_session.commit()
            return summary["tagged"], None
        except Exception as exc:
            stage_session.rollback()
            return [], exc
        finally:
            stage_session.close()

    def resolve_persons() -> tuple[int, Exception | None]:
        from library.db.engine import get_session
        from library.llm_usage.context import llm_usage_context
        from library.person_registry import resolve_document_persons

        stage_session = get_session()
        try:
            stage_doc = stage_session.get(Document, document_id)
            report(stage_session, "resolve_persons", "Osoby", 0, 0)
            with llm_usage_context(document_id=document_id):
                summary = resolve_document_persons(
                    stage_session, stage_doc, text,
                    progress_callback=lambda current, total: report(
                        stage_session, "resolve_persons", "Osoby", current, total,
                    ),
                )
            stage_session.commit()
            return len(summary["linked"]), None
        except Exception as exc:
            stage_session.rollback()
            return 0, exc
        finally:
            stage_session.close()

    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="entity-enrichment") as executor:
        place_future = executor.submit(verify_places)
        person_future = executor.submit(resolve_persons)
        result["place_tags"], place_error = place_future.result()
        result["persons_linked"], person_error = person_future.result()
    critical_errors = {
        stage: error
        for stage, error in {
            "verify_places": place_error,
            "resolve_persons": person_error,
        }.items()
        if error is not None
    }
    if critical_errors:
        raise EntityEnrichmentCriticalError(critical_errors)

    report(session, "find_pipelines", "Infrastruktura", 0, 0)
    try:
        from library.overpass_client import attach_document_pipelines

        pipeline_summary = attach_document_pipelines(
            session, document_id,
            progress_callback=lambda current, total: report(session, "find_pipelines", "Infrastruktura", current, total),
        )
        session.commit()
        result["pipelines"] = pipeline_summary["resolved"]
    except Exception as exc:
        session.rollback()
        result["warnings"].append(f"pipeline lookup: {exc}")

    report(session, "done", "Gotowe", 1, 1)
    return result
