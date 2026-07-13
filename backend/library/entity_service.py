"""Persist NER entities (persons/places) per document — MVP of docs/ner-integration-plan.md.

Sits between the NER client (library/ner_client.py) and the document_entities
table: extract → aggregate by (type, base form) → replace the document's rows.
Entities are derived data, so a refresh replaces previous rows instead of
merging (unlike doc.tags, which accumulates across runs).
"""

import logging
import re

from sqlalchemy import delete, select

from library.db.models import DocumentEntity, NerExclusion, WebDocument
from library.ner_client import aggregate_entities_detailed, extract_entities
from library.ner_normalization import normalize_ner_text

logger = logging.getLogger(__name__)


def is_excluded(exclusions: list[NerExclusion], entity_type: str, entity_text: str,
                author: str | None, raw_terms: list[str] | None = None) -> bool:
    """True when an exclusion rule suppresses this entity.

    Matching is case-insensitive on the normalized base form and, when
    provided, its raw lemmas/surface variants. entity_type='*' matches all
    types; geogName/placeName rules remain interchangeable after place-label
    merging; scope='author' only applies when the document's author matches.
    """
    candidate_keys = {
        normalize_ner_text(value).casefold()
        for value in [entity_text, *(raw_terms or [])]
        if normalize_ner_text(value)
    }
    author_lower = normalize_ner_text(author or "").casefold()
    matching_types = {entity_type}
    if entity_type in {"geogName", "placeName"}:
        matching_types.update({"geogName", "placeName"})
    for exc in exclusions:
        if exc.entity_type != "*" and exc.entity_type not in matching_types:
            continue
        if normalize_ner_text(exc.entity_text).casefold() not in candidate_keys:
            continue
        if exc.scope == "global":
            return True
        if (
            exc.scope == "author"
            and author_lower
            and normalize_ner_text(exc.author or "").casefold() == author_lower
        ):
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

    groups = aggregate_entities_detailed(raw)

    exclusions = list(session.execute(select(NerExclusion)).scalars().all())
    if exclusions:
        doc = session.get(WebDocument, document_id)
        author = getattr(doc, "author", None)
        excluded = [
            key
            for key, group in groups.items()
            if is_excluded(
                exclusions,
                key[0],
                key[1],
                author,
                raw_terms=[*group.get("raw_lemmas", []), *group.get("variants", [])],
            )
        ]
        for key in excluded:
            del groups[key]
        if excluded:
            logger.info("NER exclusions dropped %d entities for doc %s: %s",
                        len(excluded), document_id, [k[1] for k in excluded])

    session.execute(delete(DocumentEntity).where(DocumentEntity.document_id == document_id))
    rows = [
        DocumentEntity(
            document_id=document_id,
            entity_type=entity_type,
            entity_text=entity_text,
            mention_count=group["count"],
            variants=group["variants"],
        )
        for (entity_type, entity_text), group in sorted(
            groups.items(), key=lambda kv: (-kv[1]["count"], kv[0]),
        )
    ]
    session.add_all(rows)
    return rows


def get_document_entities(session, document_id: int) -> dict[str, list[dict]]:
    """Return the document's stored entities grouped by type, most-mentioned first.

    Shape: {"persName": [{"text", "count"}, ...], "geogName": [...], "placeName": [...]}.
    Place entities checked by stage-3 verification additionally carry
    "verified" (bool) and — when the geocoder resolved them — "lat"/"lon"/
    "display_name"; entities never checked have no "verified" key. Place
    entities matched to linear infrastructure (infra_geometries, Overpass)
    carry "pipeline": {"kind", "substance", "name", "geojson"}.
    Person entities resolved by stage-4 (document_persons link with
    raw_mention == entity_text) carry "person_id"/"canonical_name"/
    "person_description"/"wikidata_qid"/"confidence".
    """
    from library.db.models import InfraGeometry
    from library.person_registry import get_document_persons

    rows = (
        session.query(DocumentEntity)
        .filter(DocumentEntity.document_id == document_id)
        .order_by(DocumentEntity.mention_count.desc(), DocumentEntity.entity_text)
        .all()
    )
    persons_by_mention = {p["raw_mention"]: p for p in get_document_persons(session, document_id)}

    place_names = [r.entity_text for r in rows if r.entity_type != "persName"]
    pipelines_by_query: dict[str, InfraGeometry] = {}
    if place_names:
        infra_rows = (
            session.query(InfraGeometry)
            .filter(InfraGeometry.query.in_(place_names), InfraGeometry.resolved.is_(True))
            .all()
        )
        pipelines_by_query = {r.query: r for r in infra_rows}

    grouped: dict[str, list[dict]] = {"persName": [], "geogName": [], "placeName": []}
    for row in rows:
        item: dict = {"id": row.id, "text": row.entity_text, "count": row.mention_count,
                      "variants": row.variants or []}
        if row.geocode is not None:
            item["verified"] = row.geocode.resolved
            if row.geocode.resolved:
                item["lat"] = float(row.geocode.lat) if row.geocode.lat is not None else None
                item["lon"] = float(row.geocode.lon) if row.geocode.lon is not None else None
                item["display_name"] = row.geocode.display_name
        if row.entity_type != "persName" and row.entity_text in pipelines_by_query:
            infra = pipelines_by_query[row.entity_text]
            item["pipeline"] = {
                "kind": infra.kind,
                "substance": infra.substance,
                "name": infra.name,
                "geojson": infra.geojson,
            }
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


def filter_entities_to_text(grouped: dict[str, list[dict]], text: str) -> dict[str, list[dict]]:
    """Subset of get_document_entities() output actually mentioned in text.

    Chapter-scoped attribution: the expensive verification (geocoder, Wikidata,
    LLM) stays document-level; this only checks which of the already-verified
    entities appear in the given fragment. Stored surface variants match as
    complete tokens (Unicode-aware boundaries on both sides). Rows without
    stored variants (predating the variants column) retain the legacy
    word-start prefix fallback against entity_text until the next refresh.
    Matching is case-insensitive, except that a capitalized needle only matches
    a surface form that is also capitalized.

    Kept items get their "count" REPLACED with the local mention count and are
    re-sorted by it — the reader chip "Putin ×50" in chapter scope used to show
    the whole-book count, misleading for a chapter with a single mention.
    Original dicts are not mutated (document-level callers keep global counts).
    """
    filtered: dict[str, list[dict]] = {}
    for entity_type, items in grouped.items():
        kept = []
        for item in items:
            variants = item.get("variants") or []
            raw_needles = variants or [item["text"]]
            needles_by_key: dict[str, str] = {}
            for raw_needle in raw_needles:
                needle = raw_needle.strip()
                if needle:
                    needles_by_key.setdefault(needle.casefold(), needle)
            needles = sorted(needles_by_key.values(), key=len, reverse=True)
            if not needles:
                continue

            alternatives = "|".join(f"(?P<v{i}>{re.escape(needle)})" for i, needle in enumerate(needles))
            right_boundary = r"(?!\w)" if variants else ""
            pattern = re.compile(rf"(?<!\w)(?:{alternatives}){right_boundary}", re.IGNORECASE)

            matched_variant_indexes: set[int] = set()
            local_count = 0
            for match in pattern.finditer(text):
                variant_index = int(match.lastgroup[1:])
                needle = needles[variant_index]
                matched_text = match.group(0)
                if needle[0].isupper() and not matched_text[0].isupper():
                    continue
                matched_variant_indexes.add(variant_index)
                local_count += 1

            if local_count:
                chapter_variants = [
                    needle for i, needle in enumerate(needles) if i in matched_variant_indexes
                ]
                kept.append({**item, "count": local_count, "chapter_variants": chapter_variants})
        kept.sort(key=lambda i: (-i["count"], i["text"]))
        filtered[entity_type] = kept
    return filtered
