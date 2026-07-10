"""Resolve NER person mentions to canonical Person entities (NER stage 4).

Pipeline per docs/person-ner-plan.md: persName candidates (document_entities)
→ alias match against the internal registry → Wikidata (humans only, P31=Q5)
with LLM context disambiguation → pg_trgm fuzzy match against the registry →
document_persons links with a confidence level. Low-confidence links get
confidence=manual_review — they are queued for a human, never silently merged.

Junk guard: a mention that is a single word AND has no Wikidata human match is
skipped entirely (spaCy persName noise: product names like "Hornet",
"Starlinek" — real people are referred to by full name at least once, and the
NER lemma aggregation keeps that form).
"""

import logging
import unicodedata

from sqlalchemy import func, select

from library.db.models import DocumentEntity, DocumentPerson, Person, PersonAlias

logger = logging.getLogger(__name__)

CONFIDENCE_WIKIDATA = "wikidata_matched"
CONFIDENCE_ALIAS = "alias_matched"
CONFIDENCE_MANUAL_REVIEW = "manual_review"
CONFIDENCE_MANUAL_CONFIRMED = "manual_confirmed"

# pg_trgm similarity threshold for "possibly the same person" (queued for
# review, not auto-merged)
FUZZY_SIMILARITY_THRESHOLD = 0.5


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def label_matches_mention(mention: str, label: str) -> bool:
    """Name-consistency guard on the LLM's Wikidata pick.

    The LLM over-confirms on STT-garbled single mentions (live E2E 2026-07-10,
    doc 9216: "demokratas" -> the writer Žemaitė, "Talibanu" -> a Taliban
    commander with an unrelated name). A pick only counts when some token of
    the mention (>=3 chars, accents stripped) prefixes a token of the label or
    vice versa — "Lepen" matches "Marine Le Pen", "Macrona" matches "Emmanuel
    Macron", "demokratas" does not match "Žemaitė".
    """
    mention_tokens = [t for t in _strip_accents(mention.lower()).split() if len(t) >= 3]
    label_tokens = [t for t in _strip_accents(label.lower()).replace("-", " ").split() if len(t) >= 2]
    label_joined = "".join(label_tokens)
    for m in mention_tokens:
        if any(lt.startswith(m) or m.startswith(lt) for lt in label_tokens):
            return True
        if m in label_joined:  # "Lepen" vs "Le Pen"
            return True
    return False


def find_by_alias(session, name: str) -> Person | None:
    """Exact (case-insensitive) match on canonical name or any alias."""
    lowered = name.strip().lower()
    person = session.execute(
        select(Person).where(func.lower(Person.canonical_name) == lowered)
    ).scalars().first()
    if person is not None:
        return person
    alias = session.execute(
        select(PersonAlias).where(func.lower(PersonAlias.alias) == lowered)
    ).scalars().first()
    return alias.person if alias is not None else None


def find_fuzzy_candidate(session, name: str) -> Person | None:
    """Best pg_trgm match above threshold, canonical names and aliases alike."""
    person = session.execute(
        select(Person)
        .where(func.similarity(Person.canonical_name, name) > FUZZY_SIMILARITY_THRESHOLD)
        .order_by(func.similarity(Person.canonical_name, name).desc())
        .limit(1)
    ).scalars().first()
    if person is not None:
        return person
    alias = session.execute(
        select(PersonAlias)
        .where(func.similarity(PersonAlias.alias, name) > FUZZY_SIMILARITY_THRESHOLD)
        .order_by(func.similarity(PersonAlias.alias, name).desc())
        .limit(1)
    ).scalars().first()
    return alias.person if alias is not None else None


def _add_alias(session, person: Person, alias: str) -> None:
    existing = {a.alias.lower() for a in person.aliases}
    if alias.lower() not in existing and alias.lower() != person.canonical_name.lower():
        session.add(PersonAlias(person=person, alias=alias))


def _link(session, document_id: int, person: Person, raw_mention: str, confidence: str) -> bool:
    """Create the document<->person link unless one already exists. True if created."""
    existing = session.execute(
        select(DocumentPerson).where(
            DocumentPerson.document_id == document_id,
            DocumentPerson.person_id == person.id,
        )
    ).scalars().first()
    if existing is not None:
        return False
    session.add(DocumentPerson(
        document_id=document_id, person_id=person.id,
        raw_mention=raw_mention, confidence=confidence,
    ))
    return True


def resolve_document_persons(session, doc, text: str) -> dict:
    """Resolve the document's persName entities into document_persons links.

    Queues changes on the session without committing (caller owns the
    transaction). Returns {"linked": [(name, canonical, confidence)], "skipped": [names]}.
    """
    from library.wikidata_client import search_persons

    entities = (
        session.query(DocumentEntity)
        .filter(
            DocumentEntity.document_id == doc.id,
            DocumentEntity.entity_type == "persName",
        )
        .all()
    )

    linked: list[tuple[str, str, str]] = []
    skipped: list[str] = []
    for ent in entities:
        name = ent.entity_text.strip()

        # 1. Known alias/canonical name — cheapest, no network
        person = find_by_alias(session, name)
        if person is not None:
            if _link(session, doc.id, person, name, CONFIDENCE_ALIAS):
                linked.append((name, person.canonical_name, CONFIDENCE_ALIAS))
            continue

        # 2. Wikidata humans + LLM context disambiguation
        candidates = search_persons(name)
        if candidates:
            from library.article_tagging import confirm_person_with_llm

            qid = confirm_person_with_llm(text, doc.title or "", name, candidates)
            if qid:
                chosen = next(c for c in candidates if c["qid"] == qid)
                if not label_matches_mention(name, chosen["label"]):
                    logger.info("rejecting LLM pick %s (%r) for mention %r — name mismatch",
                                qid, chosen["label"], name)
                    qid = None
            if qid:
                person = session.execute(
                    select(Person).where(Person.wikidata_qid == qid)
                ).scalars().first()
                if person is None:
                    person = Person(
                        canonical_name=chosen["label"],
                        wikidata_qid=qid,
                        description=chosen["description"] or None,
                    )
                    session.add(person)
                    session.flush()
                _add_alias(session, person, name)
                if _link(session, doc.id, person, name, CONFIDENCE_WIKIDATA):
                    linked.append((name, person.canonical_name, CONFIDENCE_WIKIDATA))
                continue

        # 3. Junk guard: single word without a Wikidata human is spaCy noise
        if len(name.split()) < 2:
            skipped.append(name)
            continue

        # 4. Internal registry fuzzy match — possible variant of a known person,
        #    queued for review instead of auto-merging
        person = find_fuzzy_candidate(session, name)
        if person is not None:
            if _link(session, doc.id, person, name, CONFIDENCE_MANUAL_REVIEW):
                linked.append((name, person.canonical_name, CONFIDENCE_MANUAL_REVIEW))
            continue

        # 5. New, unknown person (no Wikidata entry — local/less-known figure)
        person = Person(canonical_name=name)
        session.add(person)
        session.flush()
        if _link(session, doc.id, person, name, CONFIDENCE_MANUAL_REVIEW):
            linked.append((name, person.canonical_name, CONFIDENCE_MANUAL_REVIEW))

    logger.info("person resolution doc=%s: linked=%d skipped=%d", doc.id, len(linked), len(skipped))
    return {"linked": linked, "skipped": skipped}


def get_document_persons(session, document_id: int) -> list[dict]:
    """Person links for a document, for the API/UI."""
    rows = (
        session.query(DocumentPerson)
        .filter(DocumentPerson.document_id == document_id)
        .all()
    )
    return [
        {
            "person_id": r.person_id,
            "raw_mention": r.raw_mention,
            "canonical_name": r.person.canonical_name,
            "description": r.person.description,
            "wikidata_qid": r.person.wikidata_qid,
            "confidence": r.confidence,
        }
        for r in rows
    ]
