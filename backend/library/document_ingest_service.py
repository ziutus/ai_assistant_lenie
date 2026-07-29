"""Transport-independent document ingest orchestration.

This module deliberately contains no Flask, AWS, Vault or network setup.  The
caller supplies a SQLAlchemy session and, optionally, the object storage
backend.  A missing storage is built lazily for backwards-compatible local
callers.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from library.document_service import DocumentService, ExistingDocumentError
from library.storage import ObjectStorage
from library.document_processing_service import ensure_document_prepare_job


@dataclass(frozen=True)
class IngestRequest:
    url: str
    document_type: str
    text: str = ""
    html: str = ""
    title: str = ""
    language: str = ""
    note: str = "default_note"
    paywall: bool = False
    requires_login: bool | None = None
    social_platform: str | None = None
    source: str = "own"
    ai_summary: bool = False
    chapter_list: object = False
    byline: str = ""
    original_id: str | None = None
    published_on: object | None = None
    operation: str = "create"
    external_uuid: str | None = None
    ingested_at: object | None = None


@dataclass(frozen=True)
class IngestResult:
    document_id: int
    status: str
    processing_job_id: str | None = None
    missing_raw_html: bool = False


class DocumentIngestService:
    """Apply the common create/fill contract used by API and importers."""

    def __init__(self, session: Session, storage: ObjectStorage | None = None):
        self.session = session
        self.document_service = DocumentService(session, storage=storage)

    def ingest(self, request: IngestRequest, initiated_by_user_id: int | None = None) -> IngestResult:
        del initiated_by_user_id  # Reserved for the queue contract in PR 2.
        if request.operation not in {"create", "fill_missing_html"}:
            raise ValueError("Invalid operation")
        if not request.url or not request.document_type:
            raise ValueError("Missing required parameter(s): 'url' or 'type'")

        service = self.document_service
        try:
            if request.operation == "fill_missing_html":
                doc = service.fill_missing_source_html(
                    url=request.url,
                    html=request.html,
                    text=request.text,
                    external_uuid=request.external_uuid,
                )
                job = ensure_document_prepare_job(self.session, doc) if bool(getattr(doc, "uuid", None)) else None
                return IngestResult(doc.id, "refreshed", job.id if job else None, missing_raw_html=False)

            doc = service.create_document(
                url=request.url,
                url_type=request.document_type,
                text=request.text,
                html=request.html,
                title=request.title,
                language=request.language,
                note=request.note,
                paywall=request.paywall,
                requires_login=request.requires_login,
                social_platform=request.social_platform,
                source=request.source,
                ai_summary=request.ai_summary,
                chapter_list=request.chapter_list,
                byline=request.byline,
                original_id=request.original_id,
                published_on=request.published_on,
                external_uuid=request.external_uuid,
                ingested_at=request.ingested_at,
            )
            job = (
                ensure_document_prepare_job(self.session, doc)
                if (request.document_type == "webpage" and bool(request.html) and bool(getattr(doc, "uuid", None)))
                else None
            )
            return IngestResult(
                doc.id,
                "added",
                job.id if job else None,
                missing_raw_html=not bool(request.html),
            )
        except ExistingDocumentError as exc:
            doc = exc.document
            job = (
                ensure_document_prepare_job(self.session, doc)
                if (getattr(doc, "document_type", None) == "webpage" and bool(getattr(doc, "uuid", None)))
                else None
            )
            return IngestResult(
                doc.id,
                "already_exists",
                job.id if job else None,
                missing_raw_html=not bool(getattr(doc, "text_raw", None)),
            )
