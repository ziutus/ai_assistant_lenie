"""Verify NER place candidates and tag documents with miejsce-* (NER stage 3).

Pipeline per docs/ner-integration-plan.md and docs/geo-place-ner-plan.md:
NER candidates (document_entities, geogName/placeName) → geocoder confirms the
place exists (LocationIQ + match-quality check, cached in geocode_cache) →
LLM confirms the mentions are actually about that place, not a homonymous
non-geographic proper noun (library/place_context_classifier.py — e.g.
"Wisła" as the air-defense system "Wisła-Narew-Pilica", not the river) → LLM
confirms which of the survivors the article actually discusses → tags
`miejsce-<slug>` merged into doc.tags (accumulating, like country tags).

Tags are built from the geocoder's canonical spelling (canonical_place_name on
display_name), not the NER surface form: spaCy doesn't always lemmatize proper
names, so "Kijów" and "Kijowa" arrive as separate entities — slugging the
surface form used to produce duplicate tags (miejsce-kijow + miejsce-kijowa).
Entities sharing a canonical name are grouped, and their mention counts merged,
before the context check, the AUTO_CONFIRM_MENTIONS threshold and the LLM
relevance check.

Countries are skipped entirely — they already have the kraj-* pipeline
(country_gazetteer + extract_countries_hybrid) and the map highlights them
from those tags; geocoding them here would only burn API quota.
"""

import logging
import re

from unidecode import unidecode

from library.db.models import DocumentEntity, GeocodeCache
from library.locationiq_client import canonical_place_name, geocode, is_plausible_match

logger = logging.getLogger(__name__)

PLACE_ENTITY_TYPES = ("geogName", "placeName")

# A place mentioned this many times is clearly discussed — no LLM needed.
# The LLM relevance check exists to filter out passing mentions, and mention
# count is a direct signal of that.
AUTO_CONFIRM_MENTIONS = 3


def _slugify(name: str) -> str:
    """"Cieśnina Ormuz" -> "ciesnina-ormuz" (same convention as kraj-* slugs)."""
    ascii_name = unidecode(name).lower()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name).strip("-")


def _is_country(name: str) -> bool:
    from library.country_gazetteer import detect_countries
    return bool(detect_countries(name))


def _get_or_create_geocode(session, query: str) -> GeocodeCache:
    """Cache-through geocoding: one live API call ever per distinct query string."""
    row = session.query(GeocodeCache).filter(GeocodeCache.query == query).one_or_none()
    if row is not None:
        return row

    hit = geocode(query)
    resolved = hit is not None and is_plausible_match(query, hit)
    row = GeocodeCache(
        query=query,
        resolved=resolved,
        display_name=hit.get("display_name") if hit else None,
        lat=hit.get("lat") if hit else None,
        lon=hit.get("lon") if hit else None,
        osm_class=hit.get("class") if hit else None,
        osm_type=hit.get("type") if hit else None,
        importance=hit.get("importance") if hit else None,
        raw=hit,
    )
    session.add(row)
    session.flush()  # assign id so entities can reference it
    return row


def remove_orphaned_tag(session, document, deleted_entity: DocumentEntity) -> str | None:
    """Drop a miejsce-* tag after its last supporting entity is deleted.

    verify_document_places() writes tags once, independent of document_entities
    — deleting the entity row (DELETE /website_entities/<id>) used to leave a
    stale tag behind (e.g. "Pilica" deleted from doc 9267 but miejsce-pilica
    stayed in doc.tags). Call this before the caller commits the entity
    deletion. Returns the removed tag, or None if nothing changed (entity
    wasn't a resolved place, its tag wasn't present, or another entity of this
    document still maps to the same canonical place/tag).
    """
    if deleted_entity.entity_type not in PLACE_ENTITY_TYPES:
        return None
    if deleted_entity.geocode is None or not deleted_entity.geocode.resolved:
        return None
    canonical = canonical_place_name(deleted_entity.entity_text, deleted_entity.geocode.display_name or "")
    tag = f"miejsce-{_slugify(canonical)}"
    existing = [t.strip() for t in (document.tags or "").split(",") if t.strip()]
    if tag not in existing:
        return None

    remaining = (
        session.query(DocumentEntity)
        .filter(
            DocumentEntity.document_id == document.id,
            DocumentEntity.entity_type.in_(PLACE_ENTITY_TYPES),
            DocumentEntity.id != deleted_entity.id,
            DocumentEntity.geocode_id.isnot(None),
        )
        .all()
    )
    for ent in remaining:
        if ent.geocode is not None and ent.geocode.resolved:
            other_canonical = canonical_place_name(ent.entity_text, ent.geocode.display_name or "")
            if f"miejsce-{_slugify(other_canonical)}" == tag:
                return None

    document.tags = ",".join(t for t in existing if t != tag)
    return tag


def _canonicalize_and_merge_places(session, candidates: list[DocumentEntity]) -> list[DocumentEntity]:
    """Rename entity_text to the geocoder's canonical spelling and physically
    merge document_entities rows that converge on the same canonical place
    (Faza 3 of docs/ner-multiword-place-display-names, see tmp/ plan).

    This is the same canonical_place_name() grouping verify_document_places()
    already computes for tags (module docstring) — extended to also fix what
    the reader/entities panel actually shows, not just doc.tags. Handles the
    cases text-only normalization (ner_client.py's nominative-surface
    preference) cannot: no nominative form anywhere in the text at all (e.g.
    "Zatoki Perskiej" with every mention genitive), a single unlemmatized
    one-word mention ("Gazę"), and two entities whose lemma diverged enough
    that ner_client.py's grouping never saw them as the same name at all
    ("Port Sudan" vs "Port Sudanem" — inconsistent per-token lemmatization).

    Returns the surviving entity list (deleted rows replaced by their merge
    target) so the caller's subsequent tag-building pass sees live rows.
    """
    from library.entity_service import merge_document_entities

    by_canonical: dict[str, list[DocumentEntity]] = {}
    unresolved: list[DocumentEntity] = []
    for ent in candidates:
        if ent.geocode is None or not ent.geocode.resolved:
            unresolved.append(ent)
            continue
        canonical = canonical_place_name(ent.entity_text, ent.geocode.display_name or "")
        by_canonical.setdefault(canonical, []).append(ent)

    survivors: list[DocumentEntity] = list(unresolved)
    for canonical, rows in by_canonical.items():
        # A row already spelled exactly like the canonical form is most
        # likely the one ner_client.py's Faza 1 nominative-preference
        # already got right from the text alone — anchor the merge on it
        # instead of picking by mention count, so a correct text-only result
        # is never silently overwritten by a differently-spelled duplicate.
        target = next((row for row in rows if row.entity_text == canonical), None)
        if target is None:
            target = max(rows, key=lambda row: row.mention_count)
        for row in rows:
            if row is target:
                continue
            merge_document_entities(row, target, target_source="geocoded")
            session.delete(row)
        if target.entity_text != canonical:
            target.entity_text = canonical
            target.source = "geocoded"
        survivors.append(target)
    if by_canonical:
        session.flush()
    return survivors


def verify_document_places(session, doc, text: str, progress_callback=None) -> dict:
    """Geocode the document's place entities, canonicalize/merge duplicates
    and tag confirmed places.

    Queues all changes on the session without committing (caller owns the
    transaction). Returns a summary: {"checked": int, "resolved": [names],
    "tagged": [tags]}. Countries and already-linked entities are skipped, so
    repeat runs only pay for new names.
    """
    entities = (
        session.query(DocumentEntity)
        .filter(
            DocumentEntity.document_id == doc.id,
            DocumentEntity.entity_type.in_(PLACE_ENTITY_TYPES),
        )
        .all()
    )

    checked = 0
    resolved_names: list[str] = []
    candidates = [ent for ent in entities if not _is_country(ent.entity_text)]
    for index, ent in enumerate(candidates, start=1):
        if progress_callback is not None:
            progress_callback(index, len(candidates))
        if ent.geocode_id is None:
            ent.geocode = _get_or_create_geocode(session, ent.entity_text)
            checked += 1
        if ent.geocode is not None and ent.geocode.resolved:
            resolved_names.append(ent.entity_text)

    candidates = _canonicalize_and_merge_places(session, candidates)

    # canonical name -> {"mentions": summed count, "surface": most-mentioned NER form}
    groups: dict[str, dict] = {}
    for ent in candidates:
        if ent.geocode is not None and ent.geocode.resolved:
            canonical = canonical_place_name(ent.entity_text, ent.geocode.display_name or "")
            group = groups.setdefault(canonical, {"mentions": 0, "surface": ent.entity_text, "surface_mentions": 0})
            mentions = ent.mention_count or 1
            group["mentions"] += mentions
            if mentions > group["surface_mentions"]:
                group["surface"] = ent.entity_text
                group["surface_mentions"] = mentions

    tagged: list[str] = []
    if groups:
        from library.place_context_classifier import classify_place_context_candidates

        context_results = classify_place_context_candidates(text, doc.title or "", groups, doc.id)
        if context_results:
            from library.db.models import NerContextClassification

            session.add_all([
                NerContextClassification(
                    document_id=doc.id,
                    entity_type="placeName",
                    entity_text=result["entity_text"],
                    predicted_class=result["predicted_class"],
                    confidence=result["confidence"],
                    rationale=result["rationale"],
                    context_excerpt=result["context"][:2000],
                    model=result["model"],
                    dropped=result["dropped"],
                )
                for result in context_results
            ])
            dropped_names = [result["key"] for result in context_results if result["dropped"]]
            for name in dropped_names:
                groups.pop(name, None)
            if dropped_names:
                logger.info(
                    "Context verification dropped %d non-place mentions for doc %s: %s",
                    len(dropped_names), doc.id, dropped_names,
                )

        confirmed = [name for name, g in groups.items() if g["mentions"] >= AUTO_CONFIRM_MENTIONS]
        # The LLM searches the text for mention snippets, so it gets the surface
        # form (present in the text), and confirmations map back to canonical.
        llm_surfaces = {g["surface"]: name for name, g in groups.items() if g["mentions"] < AUTO_CONFIRM_MENTIONS}
        if llm_surfaces:
            from library.article_tagging import confirm_places_with_llm

            confirmed += [
                llm_surfaces[s]
                for s in confirm_places_with_llm(text, doc.title or "", list(llm_surfaces))
                if s in llm_surfaces
            ]
        existing = [t.strip() for t in (doc.tags or "").split(",") if t.strip()]
        existing_set = set(existing)
        for name in confirmed:
            tag = f"miejsce-{_slugify(name)}"
            if tag and tag not in existing_set:
                tagged.append(tag)
                existing_set.add(tag)
        if tagged:
            doc.tags = ",".join(existing + tagged)

    logger.info(
        "place verification doc=%s: %d geocoded, %d resolved, tags: %s",
        doc.id, checked, len(resolved_names), tagged or "-",
    )
    return {"checked": checked, "resolved": resolved_names, "tagged": tagged}
