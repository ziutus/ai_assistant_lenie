"""Registry of concepts: ideologies, currents and terms worth remembering ("Ciemne oświecenie").

A ``conceptName`` mention is a manual ``document_entities`` row marked on ``/ner/:id`` (plain, document-scoped).
This module adds the canonical side:

* ``concepts`` + ``concept_aliases``: one entry per concept with a description and every name it is known by;
* ``concept_mention_links``: the reader's decision "in document D the name N means concept C", stored by
  (document, normalized name) because the mention rows are rebuilt on every NER refresh;
* the queue of mentions not linked yet, with suggestions (exact alias, then trigram similarity).

Like event names (ADR-034), a name only SUGGESTS a concept: nothing is linked until the reader says so, with one
convenience - ``auto_link_mention`` links a fresh mention at once when exactly one concept owns that exact name.
"""

from sqlalchemy import func, select

from library.db.models import Concept, ConceptAlias, ConceptMentionLink, Document, DocumentEntity
from library.geopolitics_service import name_key, normalize_text, search_key

SIMILARITY_THRESHOLD = 0.45
MAX_DOCUMENTS_LISTED = 10
MAX_NAME_LENGTH = 200
MAX_DESCRIPTION_LENGTH = 4000


class ConceptError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def _clean_name(value, field: str = "name") -> str:
    name = normalize_text(value or "") if isinstance(value, str) else ""
    if not name:
        raise ConceptError(f"{field} is required")
    if len(name) > MAX_NAME_LENGTH:
        raise ConceptError(f"{field} is too long")
    return name


def _clean_description(value) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > MAX_DESCRIPTION_LENGTH:
        raise ConceptError("Nieprawidłowy opis")
    return value.strip() or None


def _ensure_aliases(concept: Concept, names) -> None:
    have = {alias.name_key for alias in concept.aliases}
    for raw in names:
        if not isinstance(raw, str):
            continue
        alias = normalize_text(raw)
        key = name_key(alias)
        if not key or key in have or len(alias) > MAX_NAME_LENGTH:
            continue
        concept.aliases.append(ConceptAlias(alias=alias, name_key=key, search_key=search_key(alias)))
        have.add(key)


def concept_to_dict(concept: Concept, *, documents=None, document_count=None) -> dict:
    item = {
        "id": concept.id,
        "name": concept.name,
        "description": concept.description,
        "aliases": [{"id": a.id, "alias": a.alias} for a in concept.aliases],
        "created_at": concept.created_at.isoformat() if concept.created_at else None,
        "updated_at": concept.updated_at.isoformat() if concept.updated_at else None,
    }
    if document_count is not None:
        item["document_count"] = document_count
    if documents is not None:
        item["documents"] = documents
    return item


# --- the canonical registry ---------------------------------------------------------------------------------


def _documents_of(session, concept_ids) -> dict[int, list[dict]]:
    """Confirmed links per concept: one entry per document with the spellings used there."""
    ids = list(concept_ids)
    result: dict[int, dict[int, dict]] = {cid: {} for cid in ids}
    if not ids:
        return {}
    rows = session.execute(
        select(
            ConceptMentionLink.concept_id,
            ConceptMentionLink.document_id,
            ConceptMentionLink.surface,
            Document.title,
        )
        .join(Document, Document.id == ConceptMentionLink.document_id)
        .where(ConceptMentionLink.concept_id.in_(ids), ConceptMentionLink.status == "confirmed")
        .order_by(ConceptMentionLink.document_id.desc())
    ).all()
    for concept_id, document_id, surface, title in rows:
        entry = result[concept_id].setdefault(document_id, {"id": document_id, "title": title, "surfaces": []})
        if surface not in entry["surfaces"]:
            entry["surfaces"].append(surface)
    return {cid: list(docs.values()) for cid, docs in result.items()}


def list_concepts(session, *, q: str | None = None, limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
    query = select(Concept)
    needle = search_key(q) if q else ""
    if needle:
        matching = select(ConceptAlias.concept_id).where(ConceptAlias.search_key.like(f"%{needle}%"))
        query = query.where(
            Concept.id.in_(matching) | func.lower(func.coalesce(Concept.description, "")).like(f"%{needle}%")
        )
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    concepts = session.scalars(query.order_by(func.lower(Concept.name)).limit(limit).offset(offset)).all()
    documents = _documents_of(session, [c.id for c in concepts])
    items = []
    for concept in concepts:
        docs = documents.get(concept.id, [])
        items.append(concept_to_dict(concept, documents=docs[:MAX_DOCUMENTS_LISTED], document_count=len(docs)))
    return items, total


def get_concept(session, concept_id: int) -> dict:
    concept = session.get(Concept, concept_id)
    if concept is None:
        raise ConceptError("Concept not found", 404)
    docs = _documents_of(session, [concept.id]).get(concept.id, [])
    return concept_to_dict(concept, documents=docs, document_count=len(docs))


def _owner_of_key(session, key: str, *, exclude_id: int | None = None) -> int | None:
    query = select(ConceptAlias.concept_id).where(ConceptAlias.name_key == key)
    if exclude_id is not None:
        query = query.where(ConceptAlias.concept_id != exclude_id)
    return session.scalars(query).first()


def create_concept(
    session, *, name, description=None, aliases=(), user_id=None
) -> tuple[Concept, bool]:
    """A new concept, or the existing one when the name (or an alias) already belongs to a concept."""
    title = _clean_name(name)
    for candidate in (title, *[a for a in aliases if isinstance(a, str)]):
        existing_id = _owner_of_key(session, name_key(candidate))
        if existing_id is not None:
            return session.get(Concept, existing_id), False
    concept = Concept(name=title, description=_clean_description(description), created_by_user_id=user_id)
    session.add(concept)
    _ensure_aliases(concept, [title, *aliases])
    session.flush()
    return concept, True


def update_concept(session, concept_id: int, *, name=None, description=..., aliases=None) -> Concept:
    concept = session.get(Concept, concept_id)
    if concept is None:
        raise ConceptError("Concept not found", 404)
    if name is not None:
        title = _clean_name(name)
        if _owner_of_key(session, name_key(title), exclude_id=concept.id) is not None:
            raise ConceptError("Another concept already uses this name", 409)
        concept.name = title
        _ensure_aliases(concept, [title])
    if description is not ...:
        concept.description = _clean_description(description)
    if aliases is not None:
        if not isinstance(aliases, list):
            raise ConceptError("aliases must be a list")
        for raw in aliases:
            if isinstance(raw, str) and _owner_of_key(session, name_key(raw), exclude_id=concept.id) is not None:
                raise ConceptError(f"The name „{raw}” belongs to another concept", 409)
        _ensure_aliases(concept, aliases)
    session.flush()
    return concept


def remove_alias(session, concept_id: int, alias_id: int) -> None:
    alias = session.get(ConceptAlias, alias_id)
    if alias is None or alias.concept_id != concept_id:
        raise ConceptError("Alias not found", 404)
    concept = session.get(Concept, concept_id)
    if len(concept.aliases) <= 1:
        raise ConceptError("A concept needs at least one name")
    session.delete(alias)
    session.flush()


def delete_concept(session, concept_id: int) -> None:
    concept = session.get(Concept, concept_id)
    if concept is None:
        raise ConceptError("Concept not found", 404)
    session.delete(concept)
    session.flush()


# --- candidates by name -------------------------------------------------------------------------------------


def find_concepts_by_name(session, name: str, *, exclude_ids=(), limit: int = 5) -> list[dict]:
    """Registry concepts a name may mean: exact alias first, then (PostgreSQL) trigram-similar names."""
    key, folded = name_key(name), search_key(name)
    if not key:
        return []
    found: dict[int, dict] = {}
    for concept_id in session.scalars(select(ConceptAlias.concept_id).where(ConceptAlias.name_key == key)).all():
        found[concept_id] = {"reason": "alias", "score": 1.0}
    if folded and session.bind is not None and session.bind.dialect.name == "postgresql":
        similarity = func.similarity(ConceptAlias.search_key, folded)
        for concept_id, score in session.execute(
            select(ConceptAlias.concept_id, func.max(similarity))
            .where(similarity >= SIMILARITY_THRESHOLD)
            .group_by(ConceptAlias.concept_id)
        ).all():
            found.setdefault(concept_id, {"reason": "similar", "score": round(float(score), 2)})
    for concept_id in exclude_ids:
        found.pop(concept_id, None)
    if not found:
        return []
    concepts = {c.id: c for c in session.scalars(select(Concept).where(Concept.id.in_(list(found))))}
    ranked = sorted((cid for cid in found if cid in concepts), key=lambda cid: (-found[cid]["score"], cid))
    return [
        {**found[cid], "concept": {"id": cid, "name": concepts[cid].name, "description": concepts[cid].description}}
        for cid in ranked[:limit]
    ]


# --- mentions -----------------------------------------------------------------------------------------------


def _mention_rows(session, key: str | None = None):
    """``(DocumentEntity, title)`` of every concept mention; narrowed to one normalized name with ``key``."""
    rows = session.execute(
        select(DocumentEntity, Document.title)
        .join(Document, Document.id == DocumentEntity.document_id)
        .where(DocumentEntity.entity_type == "conceptName")
        .order_by(DocumentEntity.entity_text, DocumentEntity.document_id)
    ).all()
    return [(entity, title) for entity, title in rows if key is None or name_key(entity.entity_text) == key]


def unlinked_mentions(session, *, q: str | None = None, limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
    """Concept mentions with no confirmed link, grouped by normalized name, with suggestions."""
    confirmed = {
        (document_id, key)
        for document_id, key in session.execute(
            select(ConceptMentionLink.document_id, ConceptMentionLink.name_key).where(
                ConceptMentionLink.status == "confirmed"
            )
        )
    }
    rejected: dict[str, set[int]] = {}
    for key, concept_id in session.execute(
        select(ConceptMentionLink.name_key, ConceptMentionLink.concept_id).where(
            ConceptMentionLink.status == "rejected"
        )
    ):
        rejected.setdefault(key, set()).add(concept_id)
    needle = search_key(q) if q else ""
    groups: dict[str, dict] = {}
    for entity, title in _mention_rows(session):
        key = name_key(entity.entity_text)
        if (entity.document_id, key) in confirmed:
            continue
        if needle and needle not in search_key(entity.entity_text):
            continue
        group = groups.setdefault(key, {"name_key": key, "name": entity.entity_text, "mentions": 0, "documents": []})
        group["mentions"] += entity.mention_count or 0
        group["documents"].append(
            {"id": entity.document_id, "title": title, "mentions": entity.mention_count, "entity_id": entity.id}
        )
    ordered = sorted(groups.values(), key=lambda g: g["name"].casefold())
    page = ordered[offset : offset + limit]
    for group in page:
        group["document_count"] = len(group["documents"])
        group["suggestions"] = find_concepts_by_name(
            session, group["name"], exclude_ids=rejected.get(group["name_key"], ())
        )
    return page, len(ordered)


def _targets(session, key: str, document_ids=None) -> list[tuple[int, str]]:
    seen: dict[int, str] = {}
    for entity, _title in _mention_rows(session, key):
        if document_ids is None or entity.document_id in document_ids:
            seen.setdefault(entity.document_id, entity.entity_text)
    if not seen:
        raise ConceptError("No document mentions this concept name", 404)
    return list(seen.items())


def _set_links(session, key: str, concept_id: int, status: str, user_id, document_ids=None, keep_confirmed=False) -> int:
    changed = 0
    for document_id, surface in _targets(session, key, document_ids):
        link = session.scalar(
            select(ConceptMentionLink).where(
                ConceptMentionLink.document_id == document_id,
                ConceptMentionLink.name_key == key,
                ConceptMentionLink.concept_id == concept_id,
            )
        )
        if link is None:
            session.add(
                ConceptMentionLink(
                    document_id=document_id,
                    name_key=key,
                    surface=surface,
                    concept_id=concept_id,
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


def link_mentions(session, name: str, concept_id: int, *, document_ids=None, user_id=None) -> int:
    """The concept name ``name`` means registry concept ``concept_id`` (in all documents, or ``document_ids``)."""
    concept = session.get(Concept, concept_id)
    if concept is None:
        raise ConceptError("Concept not found", 404)
    key = name_key(name)
    if not key:
        raise ConceptError("name is required")
    owner = _owner_of_key(session, key, exclude_id=concept_id)
    if owner is not None:
        raise ConceptError("This name already belongs to another concept", 409)
    changed = _set_links(session, key, concept_id, "confirmed", user_id, set(document_ids) if document_ids else None)
    _ensure_aliases(concept, [name])
    session.flush()
    return changed


def reject_suggestion(session, name: str, concept_id: int, *, user_id=None) -> int:
    if session.get(Concept, concept_id) is None:
        raise ConceptError("Concept not found", 404)
    return _set_links(session, name_key(name), concept_id, "rejected", user_id, keep_confirmed=True)


def unlink_mentions(session, name: str, concept_id: int, *, document_id: int | None = None) -> int:
    query = select(ConceptMentionLink).where(
        ConceptMentionLink.name_key == name_key(name),
        ConceptMentionLink.concept_id == concept_id,
        ConceptMentionLink.status == "confirmed",
    )
    if document_id is not None:
        query = query.where(ConceptMentionLink.document_id == document_id)
    rows = session.scalars(query).all()
    if not rows:
        raise ConceptError("No such link", 404)
    for row in rows:
        session.delete(row)
    session.flush()
    return len(rows)


def create_concept_from_mention(
    session, name: str, *, description=None, user_id=None
) -> tuple[Concept, bool, int]:
    """A reader-created concept for a marked mention, linked in every document that carries the name."""
    key = name_key(name)
    targets = _targets(session, key)
    concept, created = create_concept(
        session, name=targets[0][1], description=description, aliases=[name], user_id=user_id
    )
    return concept, created, link_mentions(session, name, concept.id, user_id=user_id)


def auto_link_mention(session, document_id: int, surface: str, *, user_id=None) -> int | None:
    """Link a freshly marked mention when exactly one concept owns this exact name; its id, else ``None``."""
    key = name_key(surface)
    if not key:
        return None
    owners = set(session.scalars(select(ConceptAlias.concept_id).where(ConceptAlias.name_key == key)).all())
    if len(owners) != 1:
        return None
    concept_id = owners.pop()
    if session.scalar(
        select(ConceptMentionLink.id).where(
            ConceptMentionLink.document_id == document_id,
            ConceptMentionLink.name_key == key,
            ConceptMentionLink.concept_id == concept_id,
        )
    ):
        return concept_id
    session.add(
        ConceptMentionLink(
            document_id=document_id,
            name_key=key,
            surface=surface,
            concept_id=concept_id,
            status="confirmed",
            decided_by_user_id=user_id,
        )
    )
    session.flush()
    return concept_id
