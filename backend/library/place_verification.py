"""Verify NER place candidates and tag documents with miejsce-* (NER stage 3).

Pipeline per docs/ner-integration-plan.md and docs/geo-place-ner-plan.md:
NER candidates (document_entities, geogName/placeName) → geocoder confirms the
place exists (LocationIQ + match-quality check, cached in geocode_cache) →
LLM confirms which verified places the article actually discusses → tags
`miejsce-<slug>` merged into doc.tags (accumulating, like country tags).

Tags are built from the geocoder's canonical spelling (canonical_place_name on
display_name), not the NER surface form: spaCy doesn't always lemmatize proper
names, so "Kijów" and "Kijowa" arrive as separate entities — slugging the
surface form used to produce duplicate tags (miejsce-kijow + miejsce-kijowa).
Entities sharing a canonical name are grouped, and their mention counts merged,
before the AUTO_CONFIRM_MENTIONS threshold and the LLM relevance check.

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


def verify_document_places(session, doc, text: str) -> dict:
    """Geocode the document's place entities and tag confirmed places.

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
    # canonical name -> {"mentions": summed count, "surface": most-mentioned NER form}
    groups: dict[str, dict] = {}
    for ent in entities:
        if _is_country(ent.entity_text):
            continue
        if ent.geocode_id is None:
            ent.geocode = _get_or_create_geocode(session, ent.entity_text)
            checked += 1
        if ent.geocode is not None and ent.geocode.resolved:
            resolved_names.append(ent.entity_text)
            canonical = canonical_place_name(ent.entity_text, ent.geocode.display_name or "")
            group = groups.setdefault(canonical, {"mentions": 0, "surface": ent.entity_text, "surface_mentions": 0})
            mentions = ent.mention_count or 1
            group["mentions"] += mentions
            if mentions > group["surface_mentions"]:
                group["surface"] = ent.entity_text
                group["surface_mentions"] = mentions

    tagged: list[str] = []
    if groups:
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
