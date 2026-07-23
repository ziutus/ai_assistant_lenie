"""Persist NER entities (persons/places) per document — MVP of docs/ner-integration-plan.md.

Sits between the NER client (library/ner_client.py) and the document_entities
table: extract → aggregate by (type, base form) → replace the document's rows.
Entities are derived data, so a refresh replaces previous rows instead of
merging (unlike doc.tags, which accumulates across runs).
"""

import datetime
import logging
import re

from sqlalchemy import delete, select, update

from library.db.models import (
    Document,
    DocumentEntity,
    DocumentOrganization,
    NerContextClassification,
    NerExclusion,
    NerTemporalCandidate,
)
from library.ner_client import NERServiceUnavailable, aggregate_entities_detailed, extract_entities, is_available
from library.ner_normalization import normalize_ner_text
from library.organization_registry import merge_ner_groups, resolve_or_create

logger = logging.getLogger(__name__)
TEMPORAL_CONTEXT_WINDOW = 220
COMPACT_DATE_RE = re.compile(
    r"(?<!\d)(?:0?[1-9]|[12]\d|3[01])[./-](?:0?[1-9]|1[0-2])"
    r"(?:[./-](?:\d{2}|\d{4}))?(?!\d)"
)


def _temporal_candidate_rows(document_id: int, text: str, raw: list[dict]) -> list[NerTemporalCandidate]:
    """Locate raw NER date/time mentions in the canonical text with local context."""
    lowered = text.casefold()
    cursors: dict[str, int] = {}
    located: list[tuple[int, int, str, str, str | None]] = [
        (match.start(), match.end(), "date", match.group(0), match.group(0))
        for match in COMPACT_DATE_RE.finditer(text)
    ]
    for entity in raw:
        entity_type = entity.get("label")
        raw_text = normalize_ner_text(entity.get("text") or "")
        if entity_type not in {"date", "time"} or not raw_text:
            continue
        key = raw_text.casefold()
        start = lowered.find(key, cursors.get(key, 0))
        if start < 0:
            start = lowered.find(key)
        if start >= 0:
            cursors[key] = start + len(raw_text)
            end = start + len(raw_text)
            if any(start < known_end and end > known_start for known_start, known_end, *_ in located):
                continue
        else:
            end = start
        located.append((
            start, end, entity_type, raw_text,
            normalize_ner_text(entity.get("lemma") or "") or None,
        ))

    rows = []
    for start, end, entity_type, raw_text, lemma in sorted(located, key=lambda item: item[0]):
        excerpt = (
            text[max(0, start - TEMPORAL_CONTEXT_WINDOW):min(len(text), end + TEMPORAL_CONTEXT_WINDOW)].strip()
            if start >= 0 else raw_text
        )
        rows.append(NerTemporalCandidate(
            document_id=document_id,
            entity_type=entity_type,
            raw_text=raw_text,
            lemma=lemma,
            char_start=start if start >= 0 else None,
            context_excerpt=excerpt,
        ))
    return rows


def _record_ner_availability(session, document_id: int, *, unavailable: bool) -> None:
    """Persist doc.ner_unavailable_at immediately (own commit) — see its column comment.

    Committed independently of the caller's transaction so the flag survives
    even when the caller rolls back after refresh_document_entities raises
    (e.g. article_browser.py's except blocks).
    """
    value = datetime.datetime.utcnow() if unavailable else None
    session.execute(
        update(Document).where(Document.id == document_id).values(ner_unavailable_at=value),
    )
    session.commit()


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
    transaction) and returns the new DocumentEntity rows. When the raw
    extraction comes back empty, a cheap /healthz probe (ner_client.is_available)
    tells apart two cases — genuinely no entities (probe OK: clears any stale
    doc.ner_unavailable_at, returns []) vs. the service being down (probe
    fails: sets doc.ner_unavailable_at and raises NERServiceUnavailable). Both
    of those writes commit immediately, independent of the caller's
    transaction, so the flag survives even when the caller rolls back on the
    raised exception (e.g. article_browser.py's except blocks). Existing
    document_entities rows are left untouched on both empty-extraction paths —
    "no fresh data" must never erase previously detected entities. Entities
    matched by an ner_exclusions rule (global, or author-scoped for the
    document's author) are dropped before persisting — they never reach
    person resolution or place verification.
    """
    raw = extract_entities(text)
    if not raw:
        if is_available():
            _record_ner_availability(session, document_id, unavailable=False)
            return []
        _record_ner_availability(session, document_id, unavailable=True)
        raise NERServiceUnavailable(f"NER service unreachable while refreshing entities for document {document_id}")

    # Success: clear a stale unavailable flag as part of the caller's own
    # transaction (no isolated commit needed — unlike the branches above,
    # there is no exception here for the caller to roll back).
    doc = session.get(Document, document_id)
    if doc is not None and doc.ner_unavailable_at is not None:
        doc.ner_unavailable_at = None

    groups = aggregate_entities_detailed(raw)

    # Date/time mentions are not ordinary sidebar entities. Keep them as
    # grounded hints for the later timeline LLM stage.
    session.execute(delete(NerTemporalCandidate).where(
        NerTemporalCandidate.document_id == document_id,
    ))
    temporal_rows = _temporal_candidate_rows(document_id, text, raw)
    if temporal_rows:
        session.add_all(temporal_rows)

    exclusions = list(session.execute(select(NerExclusion)).scalars().all())
    if exclusions:
        author = getattr(doc, "byline", None)
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

    # spaCy occasionally labels a capitalized common noun as persName. Verify
    # only ambiguous one-word candidates with cheap, batched Bielik calls.
    # Fail open: malformed/unavailable LLM results leave entities untouched.
    from library.person_context_classifier import classify_single_word_person_candidates

    classifications = classify_single_word_person_candidates(
        text,
        getattr(doc, "title", None) or "",
        groups,
        document_id,
    )
    if classifications:
        session.add_all([
            NerContextClassification(
                document_id=document_id,
                entity_text=result["entity_text"],
                predicted_class=result["predicted_class"],
                confidence=result["confidence"],
                rationale=result["rationale"],
                context_excerpt=result["context"][:2000],
                model=result["model"],
                dropped=result["dropped"],
            )
            for result in classifications
        ])
        dropped_by_context = [result["key"] for result in classifications if result["dropped"]]
        for key in dropped_by_context:
            groups.pop(key, None)
        if dropped_by_context:
            logger.info(
                "Context verification dropped %d false person entities for doc %s: %s",
                len(dropped_by_context),
                document_id,
                [key[1] for key in dropped_by_context],
            )

    # orgName groups: merge same-organization spelling splits within this one
    # NER result (e.g. "Interia"/"Interii" both present as separate lemma
    # groups), then resolve each merged group against the global organizations
    # registry (docs/organization-ner-alias-plan.md). entity_text for orgName
    # becomes the registry's canonical_name so /webpage, /read and chapter
    # filtering never show the same organization twice.
    org_keys = [key for key in groups if key[0] == "orgName"]
    organization_confidence: dict[str, tuple[int, str]] = {}
    if org_keys:
        org_groups_by_name = {key[1]: groups[key] for key in org_keys}
        merged_org_groups = merge_ner_groups(org_groups_by_name)
        for key in org_keys:
            del groups[key]
        for name, group in merged_org_groups.items():
            organization, confidence = resolve_or_create(session, name, group["variants"])
            canonical_name = organization.canonical_name
            merged_key = ("orgName", canonical_name)
            existing = groups.get(merged_key)
            surface_forms = [name, *group["variants"]]
            if existing is not None:
                existing["count"] += group["count"]
                combined = dict.fromkeys(existing["variants"])
                for value in surface_forms:
                    if value.casefold() != canonical_name.casefold():
                        combined.setdefault(value, None)
                existing["variants"] = list(combined)
            else:
                distinct_variants = dict.fromkeys(
                    value for value in surface_forms if value.casefold() != canonical_name.casefold()
                )
                groups[merged_key] = {"count": group["count"], "variants": list(distinct_variants)}
            organization_confidence.setdefault(canonical_name, (organization.id, confidence))

    session.execute(delete(DocumentEntity).where(DocumentEntity.document_id == document_id))
    session.execute(delete(DocumentOrganization).where(DocumentOrganization.document_id == document_id))
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
    if organization_confidence:
        session.flush()
        rows_by_key = {(row.entity_type, row.entity_text): row for row in rows}
        for entity_text, (organization_id, confidence) in organization_confidence.items():
            row = rows_by_key.get(("orgName", entity_text))
            session.add(DocumentOrganization(
                document_id=document_id,
                organization_id=organization_id,
                document_entity_id=row.id if row is not None else None,
                confidence=confidence,
            ))

    organization_groups = [
        {
            "text": entity_text,
            "variants": group["variants"],
            "organization_id": organization_confidence.get(entity_text, (None, None))[0],
        }
        for (entity_type, entity_text), group in groups.items()
        if entity_type == "orgName"
    ]
    if doc is not None and organization_groups:
        from library.information_provenance import refresh_ner_cited_sources

        refresh_ner_cited_sources(session, doc, text, organization_groups)
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
    from library.db.models import DocumentInformationSource, DocumentOrganization, InfraGeometry
    from library.person_registry import get_document_persons

    rows = (
        session.query(DocumentEntity)
        .filter(DocumentEntity.document_id == document_id)
        .order_by(DocumentEntity.mention_count.desc(), DocumentEntity.entity_text)
        .all()
    )
    persons_by_mention = {p["raw_mention"]: p for p in get_document_persons(session, document_id)}
    source_links = session.scalars(select(DocumentInformationSource).where(
        DocumentInformationSource.document_id == document_id,
        DocumentInformationSource.role == "cited",
    )).all()
    sources_by_name = {}
    for link in source_links:
        for name in [link.source.canonical_name, link.raw_mention]:
            sources_by_name[normalize_ner_text(name).casefold()] = link
    organization_ids_by_entity = {
        link.document_entity_id: link.organization_id
        for link in session.scalars(select(DocumentOrganization).where(
            DocumentOrganization.document_id == document_id,
        )).all()
    }

    place_types = {"geogName", "placeName"}
    place_names = [r.entity_text for r in rows if r.entity_type in place_types]
    pipelines_by_query: dict[str, InfraGeometry] = {}
    if place_names:
        infra_rows = (
            session.query(InfraGeometry)
            .filter(InfraGeometry.query.in_(place_names), InfraGeometry.resolved.is_(True))
            .all()
        )
        pipelines_by_query = {r.query: r for r in infra_rows}

    grouped: dict[str, list[dict]] = {
        "persName": [], "orgName": [], "geogName": [], "placeName": [],
    }
    for row in rows:
        item: dict = {"id": row.id, "text": row.entity_text, "count": row.mention_count,
                      "variants": row.variants or []}
        if row.geocode is not None:
            item["verified"] = row.geocode.resolved
            if row.geocode.resolved:
                item["lat"] = float(row.geocode.lat) if row.geocode.lat is not None else None
                item["lon"] = float(row.geocode.lon) if row.geocode.lon is not None else None
                item["display_name"] = row.geocode.display_name
        if row.entity_type in place_types and row.entity_text in pipelines_by_query:
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
        if row.entity_type == "orgName":
            source_link = next((
                sources_by_name.get(normalize_ner_text(name).casefold())
                for name in [row.entity_text, *(row.variants or [])]
                if sources_by_name.get(normalize_ner_text(name).casefold()) is not None
            ), None)
            if source_link is not None:
                item["information_source_id"] = source_link.source_id
                item["source_evidence"] = source_link.evidence_excerpt
            organization_id = organization_ids_by_entity.get(row.id)
            if organization_id is not None:
                item["organization_id"] = organization_id
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


PLACE_TYPES = ("geogName", "placeName")
# orgName is accepted as a merge *source* (not target) to cover NER
# misclassifications where the same real-world place was tagged orgName in
# one mention and geogName/placeName in another within the same document
# (e.g. "Kijów" — see docs discussion, no dedicated doc file yet).
MERGEABLE_PLACE_SOURCE_TYPES = (*PLACE_TYPES, "orgName")


def merge_document_entities(source: DocumentEntity, target: DocumentEntity) -> None:
    """Fold source into target: sum mention_count, union variants, adopt a
    missing geocode_id from source. Caller deletes source from the session and
    owns the transaction/validation (document/type checks) — see
    POST /document/<id>/places/merge in server.py. Unlike orgName merges,
    places have no cross-document registry, so this is per-document only.
    """
    combined_variants = dict.fromkeys(target.variants or [])
    for value in [source.entity_text, *(source.variants or [])]:
        if value.casefold() != target.entity_text.casefold():
            combined_variants.setdefault(value)
    target.variants = list(combined_variants)
    target.mention_count += source.mention_count
    if target.geocode_id is None and source.geocode_id is not None:
        target.geocode_id = source.geocode_id
