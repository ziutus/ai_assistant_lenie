"""Structured document authorship — document_persons links with role="author".

web_documents.byline stays the comma-separated display cache; the source of
truth for "who wrote this" is document_persons (role="author"), one row per
co-author, resolved through the person registry so the same journalist links
to one Person row across documents. Portal journalists usually have no
Wikidata entry — they become local Person rows (wikidata_qid NULL), exactly
like person_registry's cascade step 5.

Confidence semantics on the author links:
- manual entry (reviewer typed the byline)  -> manual_confirmed
- LLM extraction, name already in registry  -> alias_matched
- LLM extraction, new/unknown name          -> manual_review (queued on
  /persons-review like any other unverified person)
"""

import logging
import re

from sqlalchemy import select

from library.db.models import DocumentPerson, Person
from library.person_registry import (
    CONFIDENCE_ALIAS,
    CONFIDENCE_MANUAL_CONFIRMED,
    CONFIDENCE_MANUAL_REVIEW,
    _delete_person_if_orphaned,
    find_by_alias,
)

logger = logging.getLogger(__name__)

# Portal bylines separate co-authors with commas, semicolons, slashes,
# newlines (multi-line copy-paste) or the Polish conjunctions "i"/"oraz"
# ("Michał Rogalski i Piotr Gruszka").
# Do not wrap the alternatives in ``\s*``: adjacent unbounded whitespace
# matches can backtrack polynomially on an untrusted pasted byline. Each split
# part is stripped below, so whitespace consumption here is unnecessary.
_AUTHOR_SEPARATORS = re.compile(r"[,;/\n]|\bi\b|\boraz\b", re.IGNORECASE)

# Portal UI junk that survives a byline copy-paste ("Michał Rogalski\nObserwuj").
_AUTHOR_STOPWORDS = {"obserwuj", "autor", "autorzy", "autorka", "red.", "redakcja", "opracowanie"}


def split_author_names(raw: str) -> list[str]:
    """Split a byline string into individual author names, deduplicated.

    Copy-pasting from a portal often duplicates each name ("Michał Rogalski
    Michał Rogalski") — dedup is case-insensitive, first occurrence wins.
    """
    names: list[str] = []
    seen: set[str] = set()
    for part in _AUTHOR_SEPARATORS.split(raw or ""):
        name = part.strip()
        if not name or name.lower() in seen or name.lower() in _AUTHOR_STOPWORDS:
            continue
        seen.add(name.lower())
        names.append(name)
    return names


def set_document_authors(session, doc, names: list[str], method: str) -> list[dict]:
    """Set the document's authors: display cache (byline) + document_persons links.

    method: "manual" (reviewer typed the byline), "llm" (byline extraction)
    or "html" (deterministic metadata extraction).
    Queues changes on the session without committing (caller owns the
    transaction). Returns the author list in get_document_authors() shape.

    Author links not in the new set are deleted (the main use case is fixing
    an LLM misfire); if the person is genuinely mentioned in the text, the
    next entity refresh re-links them as role="mentioned". Persons orphaned
    by the deletion are removed from the registry.
    """
    names = [n.strip() for n in names if n and n.strip()]
    doc.byline = ", ".join(names) or None
    doc.byline_method = method if names else None

    existing = session.execute(
        select(DocumentPerson).where(
            DocumentPerson.document_id == doc.id,
            DocumentPerson.role == "author",
        )
    ).scalars().all()
    existing_by_person = {link.person_id: link for link in existing}

    kept_person_ids: set[int] = set()
    for name in names:
        person = find_by_alias(session, name)
        if person is None:
            person = Person(canonical_name=name)
            session.add(person)
            session.flush()
            confidence = CONFIDENCE_MANUAL_CONFIRMED if method == "manual" else CONFIDENCE_MANUAL_REVIEW
        else:
            confidence = CONFIDENCE_MANUAL_CONFIRMED if method == "manual" else CONFIDENCE_ALIAS
        kept_person_ids.add(person.id)

        link = existing_by_person.get(person.id) or session.execute(
            select(DocumentPerson).where(
                DocumentPerson.document_id == doc.id,
                DocumentPerson.person_id == person.id,
            )
        ).scalars().first()
        if link is None:
            session.add(DocumentPerson(
                document_id=doc.id, person_id=person.id, raw_mention=name,
                confidence=confidence, role="author",
            ))
        else:
            # Promote a "mentioned" link (or refresh an author one). A manual
            # confirmation upgrades confidence; never downgrade an existing
            # manual_confirmed/wikidata_matched link to manual_review.
            link.role = "author"
            if method == "manual":
                link.confidence = CONFIDENCE_MANUAL_CONFIRMED

    for link in existing:
        if link.person_id not in kept_person_ids:
            person_id = link.person_id
            session.delete(link)
            session.flush()
            _delete_person_if_orphaned(session, person_id)

    session.flush()
    return get_document_authors(session, doc.id)


def get_document_authors(session, document_id: int) -> list[dict]:
    """The document's authors (role="author" links), oldest link first."""
    rows = session.execute(
        select(DocumentPerson, Person)
        .join(Person, DocumentPerson.person_id == Person.id)
        .where(
            DocumentPerson.document_id == document_id,
            DocumentPerson.role == "author",
        )
        .order_by(DocumentPerson.id)
    ).all()
    return [{
        "person_id": person.id,
        "link_id": link.id,
        "name": person.canonical_name,
        "description": person.description,
        "confidence": link.confidence,
        "wikidata_qid": person.wikidata_qid,
    } for link, person in rows]
