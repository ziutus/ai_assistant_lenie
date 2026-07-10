"""Persist NER entities (persons/places) per document — MVP of docs/ner-integration-plan.md.

Sits between the NER client (library/ner_client.py) and the document_entities
table: extract → aggregate by (type, base form) → replace the document's rows.
Entities are derived data, so a refresh replaces previous rows instead of
merging (unlike doc.tags, which accumulates across runs).
"""

import logging

from sqlalchemy import delete, select

from library.db.models import DocumentEntity, NerExclusion, WebDocument
from library.ner_client import aggregate_entities, extract_entities

logger = logging.getLogger(__name__)


def is_excluded(exclusions: list[NerExclusion], entity_type: str, entity_text: str,
                author: str | None) -> bool:
    """True when an exclusion rule suppresses this entity.

    Matching is case-insensitive on the aggregated base form; entity_type='*'
    matches all types; scope='author' rules only apply when the document's
    author matches the rule's author.
    """
    text_lower = entity_text.strip().lower()
    author_lower = (author or "").strip().lower()
    for exc in exclusions:
        if exc.entity_type not in ("*", entity_type):
            continue
        if exc.entity_text.strip().lower() != text_lower:
            continue
        if exc.scope == "global":
            return True
        if exc.scope == "author" and author_lower and (exc.author or "").strip().lower() == author_lower:
            return True
    return False


def refresh_document_entities(session, document_id: int, text: str) -> list[DocumentEntity]:
    """Run NER on text and replace the document's rows in document_entities.

    Queues the changes on the session without committing (caller owns the
    transaction). Returns the new DocumentEntity rows. When the NER service is
    unavailable an empty extraction result leaves existing rows untouched —
    "service down" must not erase previously detected entities. Entities
    matched by an ner_exclusions rule (global, or author-scoped for the
    document's author) are dropped before persisting — they never reach
    person resolution or place verification.
    """
    raw = extract_entities(text)
    if not raw:
        return []

    counts = aggregate_entities(raw)

    exclusions = list(session.execute(select(NerExclusion)).scalars().all())
    if exclusions:
        doc = session.get(WebDocument, document_id)
        author = getattr(doc, "author", None)
        excluded = [k for k in counts if is_excluded(exclusions, k[0], k[1], author)]
        for key in excluded:
            del counts[key]
        if excluded:
            logger.info("NER exclusions dropped %d entities for doc %s: %s",
                        len(excluded), document_id, [k[1] for k in excluded])

    session.execute(delete(DocumentEntity).where(DocumentEntity.document_id == document_id))
    rows = [
        DocumentEntity(
            document_id=document_id,
            entity_type=entity_type,
            entity_text=entity_text,
            mention_count=count,
        )
        for (entity_type, entity_text), count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    session.add_all(rows)
    return rows


def get_document_entities(session, document_id: int) -> dict[str, list[dict]]:
    """Return the document's stored entities grouped by type, most-mentioned first.

    Shape: {"persName": [{"text", "count"}, ...], "geogName": [...], "placeName": [...]}.
    Place entities checked by stage-3 verification additionally carry
    "verified" (bool) and — when the geocoder resolved them — "lat"/"lon"/
    "display_name"; entities never checked have no "verified" key.
    Person entities resolved by stage-4 (document_persons link with
    raw_mention == entity_text) carry "person_id"/"canonical_name"/
    "person_description"/"wikidata_qid"/"confidence".
    """
    from library.person_registry import get_document_persons

    rows = (
        session.query(DocumentEntity)
        .filter(DocumentEntity.document_id == document_id)
        .order_by(DocumentEntity.mention_count.desc(), DocumentEntity.entity_text)
        .all()
    )
    persons_by_mention = {p["raw_mention"]: p for p in get_document_persons(session, document_id)}

    grouped: dict[str, list[dict]] = {"persName": [], "geogName": [], "placeName": []}
    for row in rows:
        item: dict = {"id": row.id, "text": row.entity_text, "count": row.mention_count}
        if row.geocode is not None:
            item["verified"] = row.geocode.resolved
            if row.geocode.resolved:
                item["lat"] = float(row.geocode.lat) if row.geocode.lat is not None else None
                item["lon"] = float(row.geocode.lon) if row.geocode.lon is not None else None
                item["display_name"] = row.geocode.display_name
        if row.entity_type == "persName" and row.entity_text in persons_by_mention:
            link = persons_by_mention[row.entity_text]
            item["link_id"] = link["link_id"]
            item["person_id"] = link["person_id"]
            item["canonical_name"] = link["canonical_name"]
            item["person_description"] = link["description"]
            item["wikidata_qid"] = link["wikidata_qid"]
            item["confidence"] = link["confidence"]
        grouped.setdefault(row.entity_type, []).append(item)
    return grouped
