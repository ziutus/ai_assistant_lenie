"""Review of one information source of a document: rename, retype, approve or reject.

``GET /document/<id>/information_sources`` lists what the extractors found (``document_information_sources``). This
module is the reviewer's side of it, used by the "Źródła informacji" block on ``/ner/:id``:

* approve - the link survives every automatic refresh;
* reject  - the link is kept with ``review_status='rejected'`` (hidden from the list), so a re-detection that finds
  the same publication does not bring it back as a new proposal;
* rename / retype - a source shared with other documents is not renamed under them: this document's link moves to
  a source of the new name (found or created), while a source used only here is renamed in place. A source bound to
  an organization keeps the organization's name (rename the organization instead).
"""

from sqlalchemy import func, select

from library.db.models import DocumentInformationSource, InformationSource
from library.document_event_sources import MAX_NAME_LENGTH, SOURCE_TYPES
from library.geopolitics_service import GeopoliticsError, normalize_text
from library.information_provenance import ALLOWED_ROLES, _find_source

REVIEW_STATUSES = ("approved", "needs_review", "rejected")


def link_to_entry(link: DocumentInformationSource) -> dict:
    """The shape of one entry of ``GET /document/<id>/information_sources``."""
    return {
        "id": link.id,
        "source_id": link.source_id,
        "canonical_name": link.source.canonical_name,
        "source_type": link.source.source_type,
        "domain": link.source.domain,
        "organization_id": link.source.organization_id,
        "role": link.role,
        "raw_mention": link.raw_mention,
        "source_url": link.source_url,
        "evidence_excerpt": link.evidence_excerpt,
        "confidence": link.confidence,
        "extraction_method": link.extraction_method,
        "review_status": link.review_status,
    }


def _other_links(session, link: DocumentInformationSource) -> int:
    return session.scalar(
        select(func.count()).select_from(DocumentInformationSource).where(
            DocumentInformationSource.source_id == link.source_id, DocumentInformationSource.id != link.id,
        )
    ) or 0


def _drop_if_orphaned(session, source: InformationSource) -> None:
    """Delete a source nobody links to any more, unless it stands for an organization."""
    if source.organization_id is not None:
        return
    left = session.scalar(
        select(func.count()).select_from(DocumentInformationSource).where(
            DocumentInformationSource.source_id == source.id
        )
    )
    if not left:
        session.delete(source)


def _check_unique(session, document_id: int, source_id: int, role: str, own_id: int) -> None:
    clash = session.scalar(select(DocumentInformationSource.id).where(
        DocumentInformationSource.document_id == document_id,
        DocumentInformationSource.source_id == source_id,
        DocumentInformationSource.role == role,
        DocumentInformationSource.id != own_id,
    ))
    if clash is not None:
        raise GeopoliticsError("Ten dokument ma już takie źródło w tej roli", 409)


def update_document_source_link(session, document_id: int, link_id: int, data: dict) -> dict:
    """Apply ``name`` / ``source_type`` / ``role`` / ``review_status`` from a request body; returns the entry."""
    link = session.get(DocumentInformationSource, link_id)
    if link is None or link.document_id != document_id:
        raise GeopoliticsError("Nie znaleziono źródła tego dokumentu", 404)

    status = data.get("review_status")
    if status is not None and status not in REVIEW_STATUSES:
        raise GeopoliticsError(f"Nieznany status: {status}", 400)
    source_type = data.get("source_type")
    if source_type is not None and source_type not in SOURCE_TYPES:
        raise GeopoliticsError(f"Nieznany typ źródła: {source_type}", 400)
    role = data.get("role")
    if role is not None and role not in ALLOWED_ROLES:
        raise GeopoliticsError(f"Nieznana rola źródła: {role}", 400)
    name = normalize_text(data["name"]) if data.get("name") is not None else None
    if name is not None and (not name or len(name) > MAX_NAME_LENGTH):
        raise GeopoliticsError(f"Nazwa źródła ma mieć od 1 do {MAX_NAME_LENGTH} znaków", 400)

    source = link.source
    target = source
    if name is not None and name != source.canonical_name:
        if source.organization_id is not None:
            raise GeopoliticsError("To źródło jest organizacją: zmień nazwę organizacji w rejestrze", 400)
        existing = _find_source(session, name)
        if existing is not None and existing.id != source.id:
            target = existing
        elif _other_links(session, link) == 0:
            source.canonical_name = name
        else:
            target = InformationSource(canonical_name=name, source_type=source.source_type)
            session.add(target)
            session.flush()
    if source_type is not None:
        if target.organization_id is not None:
            raise GeopoliticsError("Typ źródła będącego organizacją zmienia się w rejestrze źródeł", 400)
        target.source_type = source_type

    new_role = role or link.role
    if target is not source or new_role != link.role:
        _check_unique(session, document_id, target.id, new_role, link.id)
    if target is not source:
        link.source_id = target.id
        link.source = target
    link.role = new_role
    if status is not None:
        link.review_status = status
    elif name is not None or source_type is not None or role is not None:
        # An edit is a decision: the link is no longer an unreviewed guess, and no refresh may wipe it.
        link.review_status = "approved"
    session.flush()
    if target is not source:
        _drop_if_orphaned(session, source)
        session.flush()
    return link_to_entry(link)
