"""A study, report or book mistaken for a world event becomes an information source instead.

The timeline extractor (``timeline_events``) and the registry of world events (ADR-034) hold *events*. A sentence
such as "w 2015 roku opublikowano badanie Towers i in. o zarażaniu przemocą" only says when a publication appeared:
it is a source of information (``information_sources`` + ``document_information_sources``, role ``cited`` or
``data_source``), not an event of the world. This module moves such entries over:

* ``convert_document_event_to_source`` — one timeline entry (``document_events``), by hand from the chapter panel;
* ``review_publication_entries`` — a bulk pass over what is already stored: timeline entries and still-proposed
  registry events of kind ``other`` that only report a publication (dry run by default).

A conversion is an explicit decision, so the new link is ``approved``: the automatic source refresh never removes it.
"""

import logging

from sqlalchemy import select

from library.db.models import (
    CountryRelationEvidence,
    DocumentEvent,
    DocumentInformationSource,
    GeoEvent,
    GeoEventSource,
)
from library.geopolitics_service import GeopoliticsError, normalize_text
from library.information_provenance import ALLOWED_ROLES, _get_or_create_source
from library.timeline_events import is_publication_statement

logger = logging.getLogger(__name__)

# What the picker offers for a publication-like source. ``source_type`` is free text in the table (30 characters),
# the closed list only keeps the UI and the extractor prompt in step.
SOURCE_TYPES = ("study", "report", "book", "institution", "agency", "newspaper", "portal", "database", "other")
DEFAULT_SOURCE_TYPE = "study"
DEFAULT_ROLE = "cited"
EXTRACTION_METHOD = "manual_from_event"
MAX_NAME_LENGTH = 200


def default_source_name(description: str) -> str:
    """A name taken from the event wording: the whole sentence when short, else cut at a word before 120 characters."""
    text = normalize_text(description).rstrip(".")
    if len(text) <= 120:
        return text
    return text[:120].rsplit(" ", 1)[0]


def _link_source(session, *, document_id: int, name: str, source_type: str, role: str, quote: str | None,
                 method: str) -> tuple[DocumentInformationSource, bool]:
    """Find or create the information source and its approved link to the document; return (link, created)."""
    source = _get_or_create_source(
        session, {"canonical_name": name, "raw_mention": name, "source_type": source_type, "domain": None},
    )
    link = session.scalar(select(DocumentInformationSource).where(
        DocumentInformationSource.document_id == document_id,
        DocumentInformationSource.source_id == source.id,
        DocumentInformationSource.role == role,
    ))
    if link is not None:
        link.review_status = "approved"
        return link, False
    link = DocumentInformationSource(
        document_id=document_id,
        source_id=source.id,
        role=role,
        raw_mention=name,
        source_url=None,
        evidence_excerpt=normalize_text(quote or "") or None,
        confidence=100,
        extraction_method=method,
        review_status="approved",
    )
    session.add(link)
    session.flush()
    return link, True


def _validated(name: str | None, description: str, source_type: str | None, role: str | None) -> tuple[str, str, str]:
    name = normalize_text(name or "") or default_source_name(description)
    if not name:
        raise GeopoliticsError("Nazwa źródła nie może być pusta", 400)
    if len(name) > MAX_NAME_LENGTH:
        raise GeopoliticsError(f"Nazwa źródła jest za długa (maksymalnie {MAX_NAME_LENGTH} znaków)", 400)
    source_type = source_type or DEFAULT_SOURCE_TYPE
    if source_type not in SOURCE_TYPES:
        raise GeopoliticsError(f"Nieznany typ źródła: {source_type}", 400)
    role = role or DEFAULT_ROLE
    if role not in ALLOWED_ROLES:
        raise GeopoliticsError(f"Nieznana rola źródła: {role}", 400)
    return name, source_type, role


def convert_document_event_to_source(
    session,
    document_event_id: int,
    *,
    name: str | None = None,
    source_type: str | None = None,
    role: str | None = None,
) -> dict:
    """Replace a timeline entry with an approved information-source link of the same document.

    409 when the entry already backs a registry event: that decision must be undone on the event first, because
    deleting the entry would silently detach the passage the event cites.
    """
    row = session.get(DocumentEvent, document_event_id)
    if row is None:
        raise GeopoliticsError("Wpis osi czasu nie istnieje", 404)
    cited_by = session.scalars(
        select(GeoEventSource.event_id).where(GeoEventSource.document_event_id == row.id)
    ).all()
    if cited_by:
        raise GeopoliticsError(
            f"Wpis jest już źródłem zdarzenia #{cited_by[0]} w rejestrze; odepnij go tam, zanim zamienisz go na źródło",
            409,
        )
    name, source_type, role = _validated(name, row.description, source_type, role)
    link, created = _link_source(
        session,
        document_id=row.document_id,
        name=name,
        source_type=source_type,
        role=role,
        quote=row.anchor_quote or row.description,
        method=EXTRACTION_METHOD,
    )
    document_id = row.document_id
    session.delete(row)
    session.flush()
    return {
        "document_id": document_id,
        "source_id": link.source_id,
        "link_id": link.id,
        "name": name,
        "source_type": source_type,
        "role": role,
        "created": created,
    }


def _registry_event_is_removable(session, event: GeoEvent) -> str | None:
    """Why a registry event may NOT be turned into sources, or None when nothing depends on it."""
    if event.status != "proposed":
        return f"status {event.status}"
    if event.kind != "other":
        return f"rodzaj {event.kind}"
    if event.participants or event.organizations or event.persons:
        return "ma uczestników"
    if session.scalar(select(CountryRelationEvidence.id).where(CountryRelationEvidence.event_id == event.id).limit(1)):
        return "jest podstawą oceny relacji"
    if not event.sources:
        return "brak cytowanych dokumentów"
    return None


def review_publication_entries(session, *, apply: bool = False, limit: int = 500) -> dict:
    """Find timeline entries and proposed registry events that only report a publication.

    A registry event is turned into sources only when nothing depends on it: still ``proposed``, kind ``other``, no
    participants, no assessment resting on it, at least one cited document. It is then ``rejected`` (never revived by
    a repeated report) and each cited document gets an approved source named after the event title. Timeline entries
    are converted the same way, named after their wording. Everything else is only listed.
    """
    report = {"timeline": [], "registry": [], "skipped": [], "applied": apply}

    entries = session.scalars(select(DocumentEvent).order_by(DocumentEvent.id).limit(limit * 4)).all()
    for row in entries:
        if not is_publication_statement(row.description):
            continue
        item = {"document_event_id": row.id, "document_id": row.document_id, "description": row.description}
        if len(report["timeline"]) >= limit:
            break
        if apply:
            try:
                with session.begin_nested():
                    item["converted"] = convert_document_event_to_source(session, row.id)
            except GeopoliticsError as exc:
                item["error"] = exc.message
        report["timeline"].append(item)

    # Every live event is examined; the ones that cannot be moved are listed with the reason, because a confirmed
    # event about a study is exactly what a human should look at.
    events = session.scalars(
        select(GeoEvent).where(GeoEvent.status != "rejected").order_by(GeoEvent.id)
    ).all()
    for event in events:
        if not is_publication_statement(event.title) and not is_publication_statement(event.description or ""):
            continue
        reason = _registry_event_is_removable(session, event)
        item = {"event_id": event.id, "title": event.title, "documents": sorted({s.document_id for s in event.sources})}
        if reason:
            item["skipped"] = reason
            report["skipped"].append(item)
            continue
        if apply:
            try:
                with session.begin_nested():
                    name = default_source_name(event.title)
                    for source in event.sources:
                        _link_source(
                            session,
                            document_id=source.document_id,
                            name=name,
                            source_type=DEFAULT_SOURCE_TYPE,
                            role=DEFAULT_ROLE,
                            quote=source.anchor_quote,
                            method=EXTRACTION_METHOD,
                        )
                    event.status = "rejected"
                    event.version += 1
            except GeopoliticsError as exc:
                item["error"] = exc.message
        report["registry"].append(item)
    return report
