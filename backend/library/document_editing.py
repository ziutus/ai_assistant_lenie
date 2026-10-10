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
    DocumentFacility,
    DocumentImage,
    DocumentInformationSource,
    DocumentOrganization,
    DocumentPerson,
    DocumentReference,
    DocumentTimePeriod,
    DocumentTone,
    Job,
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

    # Entity verification runs as a generic queue job (not a DocumentAnalysisJob).
    # Reopening while one is active would let it write places/persons for text
    # that is about to change; finished ones are history of the deleted entities.
    enrichment_scope = (
        Job.type == "entity_enrichment",
        Job.parameters["document_id"].as_integer() == document_id,
    )
    active_enrichment = session.scalar(select(Job).where(
        *enrichment_scope, Job.status.in_(("queued", "running", "cancel_requested")),
    ).limit(1))
    if active_enrichment is not None:
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
        DocumentOrganization,
        DocumentFacility,
        DocumentPerson,
        DocumentEntity,
        NerTemporalCandidate,
        DocumentAnalysisJob,
    )
    removed = {}
    for model in models:
        result = session.execute(delete(model).where(model.document_id == document_id))
        removed[model.__tablename__] = result.rowcount

    enrichment_jobs_removed = session.execute(delete(Job).where(*enrichment_scope)).rowcount

    # Place tags (miejsce-*) and the NER check markers are derived from the
    # entities deleted above; leaving them would show a document with no
    # entities as "already checked". Other tags (thematic, kraj-*) stay.
    existing_tags = [t.strip() for t in (doc.tags or "").split(",") if t.strip()]
    kept_tags = [t for t in existing_tags if not t.startswith("miejsce-")]
    place_tags_removed = len(existing_tags) - len(kept_tags)
    doc.tags = ",".join(kept_tags)
    doc.entities_checked_at = None
    doc.ner_unavailable_at = None

    doc.processing_status = StalkerDocumentStatus.NEED_CLEAN_MD.name
    doc.processing_error_code = None
    doc.quality = None
    session.commit()
    return {
        "document_id": document_id,
        "processing_status": doc.processing_status,
        "removed": removed,
        "place_tags_removed": place_tags_removed,
        "enrichment_jobs_removed": enrichment_jobs_removed,
    }
