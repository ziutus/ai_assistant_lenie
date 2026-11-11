"""World-events registry views and the decisions about named-event mentions (ADR-034).

``geo_events`` is the canonical registry (see ``geopolitics_service``). This module adds what the
``/world-events`` page needs:

* the canonical index: events with the documents that talk about them, whether as a cited source or as a named
  mention the reader linked;
* the queue of named-event mentions (``document_entities`` rows of type ``eventName``, marked by hand on
  ``/ner/:id``) that are not linked to any event yet, with suggestions;
* the decisions themselves (link, reject a suggestion, unlink), stored by (document, normalized name) because
  the mention rows are rebuilt on every NER refresh and cannot carry a decision;
* promotion of a timeline entry of one document (``document_events``) to a registry event or a source of one.

A name only ever SUGGESTS an event. "Wybory w Polsce" is a name of the 2023 and of the 2027 election alike, so
nothing is linked until the reader says so.
"""

from sqlalchemy import func, select

from library.db.models import (
    Document,
    DocumentEntity,
    DocumentEvent,
    GeoEvent,
    GeoEventAlias,
    GeoEventMentionLink,
)
from library.geopolitics_service import (
    GeopoliticsError,
    _add_source,
    _ensure_aliases,
    create_event,
    event_to_dict,
    list_events,
    name_key,
    normalize_text,
    search_key,
)

ROLE_LABELS = {
    "actor": "sprawca",
    "target": "cel",
    "affected": "dotknięty",
    "location": "miejsce",
    "host": "gospodarz",
    "organizer": "organizator",
    "winner": "zwycięzca",
    "subject": "podmiot",
}
SIMILARITY_THRESHOLD = 0.45
MAX_DOCUMENTS_LISTED = 10


# --- the canonical index ------------------------------------------------------------------------------------


def _document_titles(session, ids) -> dict[int, str | None]:
    ids = list(ids)
    if not ids:
        return {}
    return {
        doc_id: title
        for doc_id, title in session.execute(select(Document.id, Document.title).where(Document.id.in_(ids)))
    }


def world_events_index(
    session,
    *,
    q: str | None = None,
    kind: str | None = None,
    status: str | None = None,
    with_countries: bool | None = None,
    country_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """Registry events with the documents that mention them (cited sources and linked named mentions)."""
    events, total = list_events(
        session,
        q=q,
        kind=kind,
        status=status,
        with_countries=with_countries,
        country_id=country_id,
        limit=limit,
        offset=offset,
    )
    ids = [event.id for event in events]
    links: dict[int, list[tuple[int, str]]] = {event_id: [] for event_id in ids}
    if ids:
        for event_id, document_id, surface in session.execute(
            select(GeoEventMentionLink.event_id, GeoEventMentionLink.document_id, GeoEventMentionLink.surface).where(
                GeoEventMentionLink.event_id.in_(ids), GeoEventMentionLink.status == "confirmed"
            )
        ):
            links[event_id].append((document_id, surface))
    per_event_documents: dict[int, dict[int, str]] = {}
    for event in events:
        documents: dict[int, str] = {}
        for source in event.sources:
            documents.setdefault(source.document_id, "source")
        for document_id, _surface in links[event.id]:
            documents.setdefault(document_id, "mention")
        per_event_documents[event.id] = documents
    titles = _document_titles(
        session,
        {doc_id for documents in per_event_documents.values() for doc_id in list(documents)[:MAX_DOCUMENTS_LISTED]},
    )
    items = []
    for event in events:
        documents = per_event_documents[event.id]
        item = event_to_dict(event, with_documents=False)
        item["source_count"] = len(event.sources)
        item["document_count"] = len(documents)
        item["mention_names"] = sorted({surface for _doc, surface in links[event.id]})
        item["documents"] = [
            {"id": doc_id, "title": titles.get(doc_id), "via": via}
            for doc_id, via in list(documents.items())[:MAX_DOCUMENTS_LISTED]
        ]
        items.append(item)
    return items, total


# --- candidates by name ------------------------------------------------------------------------------------


def find_events_by_name(session, name: str, *, exclude_ids=(), limit: int = 5) -> list[dict]:
    """Registry events a name may mean: exact alias first, then (PostgreSQL) trigram-similar names.

    Always candidates, never a verdict: one alias can belong to several events (an election that repeats).
    """
    key, folded = name_key(name), search_key(name)
    if not key:
        return []
    found: dict[int, dict] = {}
    exact = session.scalars(select(GeoEventAlias.event_id).where(GeoEventAlias.name_key == key)).all()
    for event_id in exact:
        found[event_id] = {"reason": "alias", "score": 1.0}
    if folded and session.bind is not None and session.bind.dialect.name == "postgresql":
        similarity = func.similarity(GeoEventAlias.search_key, folded)
        rows = session.execute(
            select(GeoEventAlias.event_id, func.max(similarity))
            .where(similarity >= SIMILARITY_THRESHOLD)
            .group_by(GeoEventAlias.event_id)
        ).all()
        for event_id, score in rows:
            found.setdefault(event_id, {"reason": "similar", "score": round(float(score), 2)})
    for event_id in exclude_ids:
        found.pop(event_id, None)
    if not found:
        return []
    events = {
        event.id: event
        for event in session.scalars(
            select(GeoEvent).where(GeoEvent.id.in_(list(found)), GeoEvent.status != "rejected")
        )
    }
    ranked = sorted(
        (event_id for event_id in found if event_id in events),
        key=lambda event_id: (-found[event_id]["score"], events[event_id].event_date is None, -event_id),
    )
    return [
        {
            **found[event_id],
            "event": {
                "id": event_id,
                "title": events[event_id].title,
                "kind": events[event_id].kind,
                "event_date": events[event_id].event_date.isoformat() if events[event_id].event_date else None,
                "status": events[event_id].status,
            },
        }
        for event_id in ranked[:limit]
    ]


# --- named-event mentions -----------------------------------------------------------------------------------


def _mention_rows(session, key: str | None = None):
    """``(DocumentEntity, title)`` of every named event; filtered to one normalized name when ``key`` is given."""
    rows = session.execute(
        select(DocumentEntity, Document.title)
        .join(Document, Document.id == DocumentEntity.document_id)
        .where(DocumentEntity.entity_type == "eventName")
        .order_by(DocumentEntity.entity_text, DocumentEntity.document_id)
    ).all()
    return [(entity, title) for entity, title in rows if key is None or name_key(entity.entity_text) == key]


def unlinked_mentions(session, *, q: str | None = None, limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
    """Named-event mentions with no confirmed link to an event, grouped by normalized name, with suggestions."""
    confirmed = {
        (document_id, key)
        for document_id, key in session.execute(
            select(GeoEventMentionLink.document_id, GeoEventMentionLink.name_key).where(
                GeoEventMentionLink.status == "confirmed"
            )
        )
    }
    rejected: dict[str, set[int]] = {}
    for key, event_id in session.execute(
        select(GeoEventMentionLink.name_key, GeoEventMentionLink.event_id).where(
            GeoEventMentionLink.status == "rejected"
        )
    ):
        rejected.setdefault(key, set()).add(event_id)
    needle = search_key(q) if q else ""
    groups: dict[str, dict] = {}
    for entity, title in _mention_rows(session):
        key = name_key(entity.entity_text)
        if (entity.document_id, key) in confirmed:
            continue
        if (
            needle
            and needle not in search_key(entity.entity_text)
            and needle not in search_key(entity.description or "")
        ):
            continue
        group = groups.setdefault(
            key, {"name_key": key, "name": entity.entity_text, "description": None, "mentions": 0, "documents": []}
        )
        group["mentions"] += entity.mention_count or 0
        group["description"] = group["description"] or entity.description
        group["documents"].append(
            {"id": entity.document_id, "title": title, "mentions": entity.mention_count, "entity_id": entity.id}
        )
    ordered = sorted(groups.values(), key=lambda g: g["name"].casefold())
    page = ordered[offset : offset + limit]
    for group in page:
        group["document_count"] = len(group["documents"])
        group["suggestions"] = find_events_by_name(
            session, group["name"], exclude_ids=rejected.get(group["name_key"], ())
        )
    return page, len(ordered)


def _targets(session, key: str, document_ids=None) -> list[tuple[int, str]]:
    """``(document_id, surface)`` of the documents that carry the named event, optionally narrowed."""
    seen: dict[int, str] = {}
    for entity, _title in _mention_rows(session, key):
        if document_ids is None or entity.document_id in document_ids:
            seen.setdefault(entity.document_id, entity.entity_text)
    if not seen:
        raise GeopoliticsError("No document mentions this event name", 404)
    return list(seen.items())


def _set_links(session, key: str, event_id: int, status: str, user_id, document_ids=None, keep_confirmed=False) -> int:
    changed = 0
    for document_id, surface in _targets(session, key, document_ids):
        link = session.scalar(
            select(GeoEventMentionLink).where(
                GeoEventMentionLink.document_id == document_id,
                GeoEventMentionLink.name_key == key,
                GeoEventMentionLink.event_id == event_id,
            )
        )
        if link is None:
            session.add(
                GeoEventMentionLink(
                    document_id=document_id,
                    name_key=key,
                    surface=surface,
                    event_id=event_id,
                    status=status,
                    decided_by_user_id=user_id,
                )
            )
        elif keep_confirmed and link.status == "confirmed":
            continue
        else:
            link.status = status
            link.decided_by_user_id = user_id
        changed += 1
    session.flush()
    return changed


def link_mentions(session, name: str, event_id: int, *, document_ids=None, user_id=None) -> int:
    """The named event ``name`` means registry event ``event_id`` (in all documents, or only ``document_ids``)."""
    event = session.get(GeoEvent, event_id)
    if event is None:
        raise GeopoliticsError("Event not found", 404)
    key = name_key(name)
    if not key:
        raise GeopoliticsError("name is required")
    ids = set(document_ids) if document_ids else None
    changed = _set_links(session, key, event_id, "confirmed", user_id, ids)
    _ensure_aliases(event, [name])  # the next document that spells it this way is suggested at once
    session.flush()
    return changed


def reject_suggestion(session, name: str, event_id: int, *, user_id=None) -> int:
    """Remember that ``name`` does NOT mean ``event_id``, so it is not suggested again."""
    if session.get(GeoEvent, event_id) is None:
        raise GeopoliticsError("Event not found", 404)
    return _set_links(session, name_key(name), event_id, "rejected", user_id, keep_confirmed=True)


def unlink_mentions(session, name: str, event_id: int, *, document_id: int | None = None) -> int:
    key = name_key(name)
    query = select(GeoEventMentionLink).where(
        GeoEventMentionLink.name_key == key,
        GeoEventMentionLink.event_id == event_id,
        GeoEventMentionLink.status == "confirmed",
    )
    if document_id is not None:
        query = query.where(GeoEventMentionLink.document_id == document_id)
    rows = session.scalars(query).all()
    if not rows:
        raise GeopoliticsError("No such link", 404)
    for row in rows:
        session.delete(row)
    session.flush()
    return len(rows)


def create_event_from_mention(
    session, name: str, *, kind: str = "other", event_date=None, description=None, user_id=None
) -> tuple[GeoEvent, bool, int]:
    """A reader-created registry event for a named mention, linked in every document that carries the name."""
    key = name_key(name)
    targets = _targets(session, key)
    title = normalize_text(targets[0][1])
    event, created = create_event(
        session,
        title=title,
        event_date=event_date,
        description=description,
        kind=kind,
        aliases=[name],
        status="confirmed",
        user_id=user_id,
    )
    return event, created, link_mentions(session, name, event.id, user_id=user_id)


# --- the timeline of one document ----------------------------------------------------------------------------


def _timeline_date(row: DocumentEvent) -> str | None:
    """The date text for ``create_event`` when the timeline entry is dated to a day, month or year."""
    if row.event_date is None or row.date_precision not in ("day", "month", "year"):
        return None
    if row.date_precision == "year":
        return f"{row.event_date.year:04d}"
    if row.date_precision == "month":
        return f"{row.event_date.year:04d}-{row.event_date.month:02d}"
    return row.event_date.isoformat()


def promote_document_event(
    session,
    document_event_id: int,
    *,
    event_id: int | None = None,
    title: str | None = None,
    kind: str = "other",
    user_id=None,
) -> tuple[GeoEvent, bool]:
    """Turn a timeline entry of one document into a registry event, or into a source of an existing one."""
    row = session.get(DocumentEvent, document_event_id)
    if row is None:
        raise GeopoliticsError("Timeline entry not found", 404)
    quote = normalize_text(row.anchor_quote or row.description or "")
    source = {"document_id": row.document_id, "quote": quote, "document_event_id": row.id}
    if event_id is not None:
        event = session.get(GeoEvent, event_id)
        if event is None:
            raise GeopoliticsError("Event not found", 404)
        _add_source(session, event, source)
        return event, False
    description = normalize_text(row.description or "")
    heading = normalize_text(title or "") or (
        description[:120].rsplit(" ", 1)[0] if len(description) > 120 else description
    )
    date_text = _timeline_date(row)
    if date_text is None and row.date_text:
        description = normalize_text(f"{description} Data w tekście: „{row.date_text}”.")
    return create_event(
        session,
        title=heading,
        event_date=date_text,
        description=description or None,
        kind=kind,
        source=source,
        user_id=user_id,
    )
