"""Durable processing for webpage documents."""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from library.article_pipeline import extract_article
from library.article_cleaner import clean_article_text
from library.db.models import Document, Job
from library.job_queue import enqueue, heartbeat
from library.storage import ObjectStorage


DOCUMENT_PREPARE = "document_prepare"

# Below this many characters of cleaned article text the fetched page is treated
# as an empty / login-wall / anti-bot response rather than a real article.
_MIN_ARTICLE_CHARS = 200


def document_prepare_idempotency_key(document_id: int, document_uuid: str) -> str:
    return f"document_prepare:{document_id}:{document_uuid}"


def ensure_document_prepare_job(session: Session, document: Document, user_id: int | None = None) -> Job:
    """Return an active prepare job, recovering an old failed/inconsistent one."""
    document_type = getattr(document, "document_type", None)
    document_uuid = getattr(document, "uuid", None)
    if document_type != "webpage" or not document_uuid:
        raise ValueError("document_prepare requires a webpage with uuid")

    key = document_prepare_idempotency_key(document.id, document_uuid)
    existing = session.scalars(select(Job).where(Job.idempotency_key == key)).one_or_none()
    if existing is not None:
        # Re-queue a finished job that produced nothing usable — the recovery
        # path after a link->webpage promotion whose first fetch hit a login
        # wall and left the document with no text_md.
        if existing.status in {"failed", "cancelled", "done"} and not document.text_md:
            existing.status = "queued"
            existing.error = None
            existing.result = None
            existing.progress = None
            existing.available_at = datetime.now(timezone.utc)
            existing.started_at = existing.heartbeat_at = existing.finished_at = None
            session.commit()
        return existing

    return enqueue(
        session,
        DOCUMENT_PREPARE,
        {"document_id": document.id, "document_uuid": document_uuid},
        idempotency_key=key,
        user_id=user_id,
    )


class DocumentJobCancelled(RuntimeError):
    pass


class StaleDocumentJob(RuntimeError):
    pass


class DocumentProcessingService:
    def __init__(self, session: Session, storage: ObjectStorage, work_dir: str):
        self.session = session
        self.storage = storage
        self.work_dir = Path(work_dir)

    def _check_cancelled(self, job: Job) -> None:
        current = self.session.get(Job, job.id)
        if current is not None and current.status == "cancel_requested":
            raise DocumentJobCancelled("document job cancellation requested")

    def _progress(self, job: Job, phase: str, document_id: int) -> None:
        self._check_cancelled(job)
        heartbeat(self.session, job.id, {"phase": phase, "document_id": document_id})

    def _upload_artifacts(self, scratch: Path, document_id: int) -> int:
        count = 0
        prefix = f"cache/markdown/{document_id}"
        for path in scratch.rglob("*"):
            if not path.is_file():
                continue
            key = f"{prefix}/{path.name}"
            self.storage.put_bytes(key, path.read_bytes())
            count += 1
        return count

    def execute(self, job: Job) -> dict:
        document_id = int(job.parameters["document_id"])
        expected_uuid = job.parameters["document_uuid"]
        document = self.session.get(Document, document_id)
        if document is None:
            raise StaleDocumentJob(f"document {document_id} no longer exists")
        if document.uuid != expected_uuid:
            raise StaleDocumentJob(f"document {document_id} uuid changed")
        if document.text_md:
            return {
                "document_id": document_id,
                "markdown_created": False,
                "llm_extracted": True,
                "artifacts_uploaded": 0,
            }

        scratch = self.work_dir / "document-jobs" / job.id / str(document_id)
        scratch.mkdir(parents=True, exist_ok=True)
        self._progress(job, "materialize_source", document_id)

        raw_key = f"cache/markdown/{document_id}/{document_id}_step_1_all.md"
        raw_path = scratch / f"{document_id}_step_1_all.md"
        if self.storage.exists(raw_key):
            raw_path.write_bytes(self.storage.get_bytes(raw_key))
        else:
            html_key = f"{document.uuid}.html"
            if not self.storage.exists(html_key):
                raise RuntimeError(f"source HTML missing from object storage: {html_key}")
            (scratch / f"{document_id}.html").write_bytes(self.storage.get_bytes(html_key))

        self._progress(job, "html_to_markdown", document_id)
        markdown_text, article = extract_article(
            document,
            str(scratch),
            verbose=False,
            operation="document_prepare",
            storage=self.storage,
        )
        if not markdown_text:
            raise RuntimeError("HTML to Markdown conversion failed")

        self._progress(job, "llm_extract", document_id)

        cleaned = clean_article_text(article, document.url) if article else {"text": ""}
        # A login wall / anti-bot page returns HTTP 200 with markup but no real
        # article. Surface it as an error on the document (visible on /list)
        # instead of only failing the job — the user then recaptures via the
        # browser extension. This also fixes the previously-silent failure for
        # extension-captured pages that yield nothing.
        if not article or len((cleaned.get("text") or "").strip()) < _MIN_ARTICLE_CHARS:
            document.set_processing_status("ERROR")
            document.set_processing_error_code("ERROR_DOWNLOAD")
            self.session.commit()
            return {
                "document_id": document_id,
                "markdown_created": False,
                "llm_extracted": bool(article),
                "artifacts_uploaded": 0,
                "content_empty": True,
            }

        document.text_extracted = article
        document.text_md = cleaned["text"]
        if cleaned.get("info_sources"):
            from library.information_provenance import refresh_rule_based_sources

            refresh_rule_based_sources(self.session, document, cleaned["info_sources"])

        self._progress(job, "upload_artifacts", document_id)
        artifacts_uploaded = self._upload_artifacts(scratch, document_id)
        self.session.commit()
        shutil.rmtree(scratch, ignore_errors=True)
        return {
            "document_id": document_id,
            "markdown_created": True,
            "llm_extracted": True,
            "artifacts_uploaded": artifacts_uploaded,
        }


def execute_document_prepare(session: Session, job: Job, storage: ObjectStorage, work_dir: str) -> dict:
    return DocumentProcessingService(session, storage, work_dir).execute(job)
