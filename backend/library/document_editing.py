"""Content edit locking and explicit invalidation of document-derived data."""

from sqlalchemy import delete, func, select

from library.db.models import (
    Document,
    DocumentAnalysisJob,
    DocumentAnalysisRun,
    DocumentCitedPublication,
    DocumentEmbedding,
    DocumentEntity,
    DocumentEvent,
    DocumentImage,
    DocumentInformationSource,
    DocumentPerson,
    DocumentReference,
    DocumentTimePeriod,
    DocumentTone,
    NerTemporalCandidate,
)
from library.models.stalker_document_status import StalkerDocumentStatus


def document_has_embeddings(session, document_id: int) -> bool:
    count = session.scalar(
        select(func.count()).select_from(DocumentEmbedding)
        .where(DocumentEmbedding.document_id == document_id)
    )
    return bool(count) if isinstance(count, (int, bool)) else False


def reopen_document_for_editing(session, document_id: int) -> dict:
    """Delete active derived data and return a document to Markdown review."""
    doc = session.get(Document, document_id)
    if doc is None:
        raise LookupError("Document not found")

    active_job = session.scalar(select(DocumentAnalysisJob).where(
        DocumentAnalysisJob.document_id == document_id,
        DocumentAnalysisJob.status.in_(("queued", "running")),
    ).limit(1))
    if active_job is not None:
        raise RuntimeError("Document analysis is still running")

    models = (
        DocumentEmbedding,
        DocumentCitedPublication,
        DocumentImage,
        DocumentAnalysisRun,
        DocumentReference,
        DocumentEvent,
        DocumentTimePeriod,
        DocumentTone,
        DocumentInformationSource,
        DocumentPerson,
        DocumentEntity,
        NerTemporalCandidate,
        DocumentAnalysisJob,
    )
    removed = {}
    for model in models:
        result = session.execute(delete(model).where(model.document_id == document_id))
        removed[model.__tablename__] = result.rowcount

    doc.processing_status = StalkerDocumentStatus.NEED_CLEAN_MD.name
    doc.processing_error_code = None
    doc.quality = None
    session.commit()
    return {"document_id": document_id, "processing_status": doc.processing_status, "removed": removed}
