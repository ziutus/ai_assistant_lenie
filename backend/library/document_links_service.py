"""Domain rules for typed, directed links between two library documents.

A ``DocumentLink`` says "document A stands in relation R to document B" — e.g.
a LinkedIn post ``discusses`` the GitHub repository it is about. The link is
stored once (``from_document_id`` → ``to_document_id``); every reader surface
renders it from both endpoints, so each relation carries a phrase for the
``from`` side and one for the ``to`` side.

Auto-detection: ``detect_url_mention_links()`` scans a document's text for
URLs that resolve to another document already in the library and proposes a
``references`` link (``status='proposed'``) — a human accepts it with one
click via ``PATCH /document_links/<id>``.
"""

import datetime as dt
import re
from urllib.parse import urlparse

from sqlalchemy import or_, select

from library.db.models import Document, DocumentLink


# relation -> (phrase when the current document is the SUBJECT/from side,
#              phrase when the current document is the OBJECT/to side)
RELATIONS: dict[str, tuple[str, str]] = {
    "references": ("Odsyła do", "Przywoływane w"),
    "discusses": ("Omawia", "Omawiane w"),
    "summarizes": ("Streszcza", "Streszczone w"),
    "updates": ("Aktualizuje", "Zaktualizowane przez"),
    "translates": ("Tłumaczenie", "Przetłumaczone w"),
    "responds_to": ("Odpowiedź na", "Odpowiedzi"),
    "related": ("Powiązane z", "Powiązane z"),
    "duplicates": ("Duplikat", "Duplikat"),
}
# Relations whose two directions mean the same thing — the picker still stores
# one row, but there is no "wrong way round" to worry about.
SYMMETRIC_RELATIONS = {"related", "duplicates"}

ALLOWED_STATUSES = {"proposed", "confirmed", "rejected"}
ALLOWED_DETECTION_METHODS = {"manual", "url_mention", "llm"}

_MAX_NOTE_LENGTH = 500
_URL_RE = re.compile(r"https?://[^\s<>\"')\]]+", re.IGNORECASE)


class DocumentLinkError(ValueError):
    """Raised for an invalid link request (bad relation, self-link, ...)."""


def validate_relation(relation: object) -> str:
    if relation not in RELATIONS:
        raise DocumentLinkError(
            "relation must be one of: " + ", ".join(sorted(RELATIONS))
        )
    return relation


def validate_status(status: object) -> str:
    if status not in ALLOWED_STATUSES:
        raise DocumentLinkError("status must be one of: " + ", ".join(sorted(ALLOWED_STATUSES)))
    return status


def _validate_note(note: object) -> str | None:
    if note is None:
        return None
    if not isinstance(note, str):
        raise DocumentLinkError("note must be a string")
    value = note.strip()
    if not value:
        return None
    if len(value) > _MAX_NOTE_LENGTH:
        raise DocumentLinkError(f"note must be at most {_MAX_NOTE_LENGTH} characters")
    return value


def _normalize_url(url: str | None) -> str | None:
    """Fold a URL to a comparable key: lowercase host, no ``www.``, no scheme,
    no trailing slash, no fragment. Good enough to match a plain-text mention
    against ``documents.url`` / ``documents.canonical_url``."""
    if not url:
        return None
    raw = url.strip()
    if not raw:
        return None
    if "://" not in raw:
        raw = "https://" + raw
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if not host or "." not in host or any(ch.isspace() for ch in host):
        return None
    path = parsed.path.rstrip("/")
    key = host + path
    if parsed.query:
        key += "?" + parsed.query
    return key


def _document_brief(doc: Document) -> dict:
    return {
        "id": doc.id,
        "title": doc.title or doc.url,
        "url": doc.url,
        "document_type": doc.document_type,
        "byline": doc.byline,
        "published_on": doc.published_on.isoformat() if doc.published_on else None,
    }


def _related_document(link: DocumentLink, attr: str) -> Document | None:
    """Read a link endpoint relationship, tolerating a detached/unloaded row."""
    try:
        return getattr(link, attr)
    except Exception:  # DetachedInstanceError and friends
        return None


def link_to_dict(link: DocumentLink, *, perspective_document_id: int | None = None) -> dict:
    """Serialize a link. When ``perspective_document_id`` is given, ``direction``
    / ``label`` / ``other_document`` are resolved relative to that document so
    the frontend can render the entry without knowing the relation vocabulary."""
    forward_label, backward_label = RELATIONS.get(link.relation, (link.relation, link.relation))
    result = {
        "id": link.id,
        "relation": link.relation,
        "status": link.status,
        "detection_method": link.detection_method,
        "note": link.note,
        "from_document_id": link.from_document_id,
        "to_document_id": link.to_document_id,
        "created_at": link.created_at.isoformat() if link.created_at else None,
        "decided_at": link.decided_at.isoformat() if link.decided_at else None,
    }
    from_document = _related_document(link, "from_document")
    to_document = _related_document(link, "to_document")
    if from_document is not None:
        result["from_document"] = _document_brief(from_document)
    if to_document is not None:
        result["to_document"] = _document_brief(to_document)
    if perspective_document_id is not None:
        if perspective_document_id == link.from_document_id:
            result["direction"] = "outgoing"
            result["label"] = forward_label
            result["other_document"] = result.get("to_document")
        else:
            result["direction"] = "incoming"
            result["label"] = backward_label
            result["other_document"] = result.get("from_document")
    return result


def list_document_links(session, document_id: int, *, include_rejected: bool = False) -> list[dict]:
    """Every link touching ``document_id``, newest first, each resolved from
    that document's perspective."""
    stmt = select(DocumentLink).where(
        or_(
            DocumentLink.from_document_id == document_id,
            DocumentLink.to_document_id == document_id,
        )
    )
    if not include_rejected:
        stmt = stmt.where(DocumentLink.status != "rejected")
    stmt = stmt.order_by(DocumentLink.status, DocumentLink.created_at.desc())
    links = session.scalars(stmt).all()
    return [link_to_dict(link, perspective_document_id=document_id) for link in links]


def create_link(
    session,
    from_document_id: int,
    to_document_id: int,
    relation: object,
    *,
    note: object = None,
    status: str = "confirmed",
    detection_method: str = "manual",
    created_by_user_id: int | None = None,
    commit: bool = True,
) -> DocumentLink:
    relation = validate_relation(relation)
    status = validate_status(status)
    if detection_method not in ALLOWED_DETECTION_METHODS:
        raise DocumentLinkError("invalid detection_method")
    if not isinstance(from_document_id, int) or not isinstance(to_document_id, int):
        raise DocumentLinkError("document ids must be integers")
    if from_document_id == to_document_id:
        raise DocumentLinkError("a document cannot be linked to itself")
    note = _validate_note(note)

    documents = session.scalars(
        select(Document).where(Document.id.in_({from_document_id, to_document_id}))
    ).all()
    found = {doc.id for doc in documents}
    missing = {from_document_id, to_document_id} - found
    if missing:
        raise DocumentLinkError(f"unknown document id(s): {sorted(missing)}")

    existing = session.scalar(
        select(DocumentLink).where(
            DocumentLink.from_document_id == from_document_id,
            DocumentLink.to_document_id == to_document_id,
            DocumentLink.relation == relation,
        )
    )
    if existing is not None:
        # Re-proposing an edge a human already rejected stays rejected; a
        # manual create revives it.
        if detection_method == "url_mention":
            return existing
        existing.status = status
        existing.note = note if note is not None else existing.note
        existing.detection_method = detection_method
        existing.decided_at = dt.datetime.now(dt.timezone.utc)
        if commit:
            session.commit()
        return existing

    link = DocumentLink(
        from_document_id=from_document_id,
        to_document_id=to_document_id,
        relation=relation,
        note=note,
        status=status,
        detection_method=detection_method,
        created_by_user_id=created_by_user_id,
        decided_at=dt.datetime.now(dt.timezone.utc) if status != "proposed" else None,
    )
    session.add(link)
    if commit:
        session.commit()
    else:
        session.flush()
    return link


def set_link_status(session, link: DocumentLink, status: object, *, commit: bool = True) -> DocumentLink:
    status = validate_status(status)
    link.status = status
    link.decided_at = dt.datetime.now(dt.timezone.utc)
    if commit:
        session.commit()
    return link


def delete_link(session, link: DocumentLink, *, commit: bool = True) -> None:
    session.delete(link)
    if commit:
        session.commit()


def _document_text(doc: Document) -> str:
    return "\n".join(part for part in (doc.text_md, doc.text, doc.summary) if part)


def detect_url_mention_links(session, document_id: int, *, commit: bool = True) -> list[DocumentLink]:
    """Propose a ``references`` link for every other library document whose URL
    is mentioned verbatim in ``document_id``'s text. Idempotent: an existing
    edge (in any status) is left untouched."""
    doc = session.get(Document, document_id)
    if doc is None:
        raise DocumentLinkError(f"unknown document id: {document_id}")

    text = _document_text(doc)
    if not text:
        return []

    mentioned_keys = {
        key for key in (_normalize_url(match.group(0)) for match in _URL_RE.finditer(text)) if key
    }
    # A bare "github.com/user/repo" (no scheme) is common in social posts.
    for match in re.finditer(r"(?<![\w/@.])((?:[a-z0-9-]+\.)+[a-z]{2,}/[^\s<>\"')\]]+)", text, re.IGNORECASE):
        key = _normalize_url(match.group(1))
        if key:
            mentioned_keys.add(key)
    if not mentioned_keys:
        return []

    self_key = _normalize_url(doc.url)
    # Narrow to documents whose URL contains one of the mentioned host+path
    # keys — the last path segment is a cheap, selective ILIKE needle. The
    # exact match still runs on the normalized keys below.
    needles = {key.rsplit("/", 1)[-1] for key in mentioned_keys if "/" in key}
    needles = {needle for needle in needles if len(needle) >= 3}
    if not needles:
        return []
    url_filters = []
    for needle in needles:
        pattern = f"%{needle}%"
        url_filters.append(Document.url.ilike(pattern))
        url_filters.append(Document.canonical_url.ilike(pattern))
    candidates = session.scalars(
        select(Document).where(Document.id != document_id, or_(*url_filters))
    ).all()

    created: list[DocumentLink] = []
    for other in candidates:
        keys = {_normalize_url(other.url), _normalize_url(other.canonical_url)} - {None, self_key}
        if not keys & mentioned_keys:
            continue
        already = session.scalar(
            select(DocumentLink).where(
                DocumentLink.from_document_id == document_id,
                DocumentLink.to_document_id == other.id,
                DocumentLink.relation == "references",
            )
        )
        if already is not None:
            continue
        link = DocumentLink(
            from_document_id=document_id,
            to_document_id=other.id,
            relation="references",
            status="proposed",
            detection_method="url_mention",
        )
        session.add(link)
        created.append(link)
    if created:
        session.flush()
        if commit:
            session.commit()
    return created
