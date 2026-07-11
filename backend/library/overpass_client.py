"""Overpass API client: pipeline geometries by name for the reader map.

Open Infrastructure Map (openinframap.org) renders OSM infrastructure data;
we query the same source directly through the Overpass API. When an article
discusses a pipeline ("Baltic Pipe", "Nord Stream"), the geocoder can't
verify it (LocationIQ returns point hits, and man_made isn't a plausible
place class) — but Overpass can return its actual route, which the reader
map draws as a polyline.

Cache-through via the infra_geometries table (one live call ever per distinct
name, negative results cached), mirroring geocode_cache. Overpass is a shared
community service — requests are rate-limited and every failure degrades to
"not resolved" without breaking the entity refresh.

Data © OpenStreetMap contributors (ODbL).
"""

import logging
import re
import time

import requests

from library.db.models import InfraGeometry

logger = logging.getLogger(__name__)

DEFAULT_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
REQUEST_TIMEOUT_S = 90

# overpass-api.de rejects generic client UAs with 406 — identify the app.
USER_AGENT = "lenie-ai/0.3 (personal research assistant; https://www.lenie-ai.eu)"


class OverpassUnavailable(Exception):
    """Transport-level Overpass failure — retryable, must NOT be cached as a miss."""

# Overpass etiquette: a shared free service. 2s spacing between live calls.
MIN_REQUEST_INTERVAL_S = 2.0
_last_request_at = 0.0

# A pipeline route can have thousands of nodes; the map only needs the shape.
MAX_POINTS_PER_LINE = 200
# Cap matched OSM elements per name (popular names could match hundreds).
MAX_ELEMENTS = 60

# Only try names that can plausibly be infrastructure: at least this long and
# capitalized (NER junk like "dom" or single letters never reaches Overpass).
MIN_QUERY_LENGTH = 4


def _overpass_url() -> str:
    from library.config_loader import load_config
    return (load_config().get("OVERPASS_URL") or DEFAULT_OVERPASS_URL).rstrip("/")


def _overpass_regex(name: str) -> str:
    """Anchored, case-insensitive-safe regex for an OSM name match.

    re.escape covers POSIX ERE metacharacters too; double quotes would end the
    Overpass string literal, so names containing them are rejected upstream.
    """
    return f"^{re.escape(name.strip())}$"


def fetch_pipeline(name: str) -> dict | None:
    """Live Overpass lookup of a pipeline by exact (case-insensitive) name.

    Returns {"name", "substance", "wikidata_qid", "geojson"} with a GeoJSON
    MultiLineString (lon/lat order, per spec), or None on a clean miss.
    Raises OverpassUnavailable on transport failures — a flaky shared server
    must not poison the cache with false misses. Callers must cache results
    (infra_geometries) — this performs a live call.
    """
    global _last_request_at

    name = (name or "").strip()
    if len(name) < MIN_QUERY_LENGTH or '"' in name:
        return None

    pattern = _overpass_regex(name)
    query = (
        f'[out:json][timeout:{REQUEST_TIMEOUT_S - 15}];'
        f'(way["man_made"="pipeline"]["name"~"{pattern}",i];'
        f'relation["man_made"="pipeline"]["name"~"{pattern}",i];'
        f'relation["type"="route"]["route"="pipeline"]["name"~"{pattern}",i];);'
        f'out geom {MAX_ELEMENTS};'
    )

    wait = MIN_REQUEST_INTERVAL_S - (time.monotonic() - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    _last_request_at = time.monotonic()

    try:
        resp = requests.post(
            _overpass_url(),
            data={"data": query},
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT_S,
        )
        resp.raise_for_status()
        elements = resp.json().get("elements", [])
    except requests.RequestException as e:
        logger.warning("Overpass request failed for %r: %s", name, e)
        raise OverpassUnavailable(str(e)) from e
    except ValueError as e:
        logger.warning("Overpass returned invalid JSON for %r: %s", name, e)
        raise OverpassUnavailable(str(e)) from e

    lines = _elements_to_lines(elements)
    if not lines:
        return None

    tags = [el.get("tags", {}) for el in elements]
    return {
        "name": next((t["name"] for t in tags if t.get("name")), name),
        "substance": next((t["substance"] for t in tags if t.get("substance")), None),
        "wikidata_qid": next((t["wikidata"] for t in tags if t.get("wikidata")), None),
        "geojson": {"type": "MultiLineString", "coordinates": lines},
    }


def _elements_to_lines(elements: list[dict]) -> list[list[list[float]]]:
    """Overpass `out geom` elements -> simplified MultiLineString coordinates.

    Ways carry their geometry directly; relations carry it per member. Each
    line is downsampled to MAX_POINTS_PER_LINE (first/last points kept) —
    enough for a country-scale map, a fraction of the payload.
    """
    lines: list[list[list[float]]] = []
    for el in elements:
        if el.get("type") == "way" and el.get("geometry"):
            lines.append(_simplify([[p["lon"], p["lat"]] for p in el["geometry"]]))
        elif el.get("type") == "relation":
            for member in el.get("members", []):
                if member.get("geometry"):
                    lines.append(_simplify([[p["lon"], p["lat"]] for p in member["geometry"]]))
    return [ln for ln in lines if len(ln) >= 2]


def _simplify(points: list[list[float]], max_points: int = MAX_POINTS_PER_LINE) -> list[list[float]]:
    if len(points) <= max_points:
        return points
    step = (len(points) - 1) / (max_points - 1)
    sampled = [points[round(i * step)] for i in range(max_points - 1)]
    return sampled + [points[-1]]


def get_or_fetch_pipeline(session, name: str) -> InfraGeometry:
    """Cache-through pipeline lookup: one live Overpass call ever per name.

    Propagates OverpassUnavailable — transport failures are not cached.
    """
    row = session.query(InfraGeometry).filter(InfraGeometry.query == name).one_or_none()
    if row is not None:
        return row

    hit = fetch_pipeline(name)
    row = InfraGeometry(
        query=name,
        resolved=hit is not None,
        kind="pipeline" if hit else None,
        substance=hit.get("substance") if hit else None,
        name=hit.get("name") if hit else None,
        wikidata_qid=hit.get("wikidata_qid") if hit else None,
        geojson=hit.get("geojson") if hit else None,
    )
    session.add(row)
    session.flush()
    return row


def attach_document_pipelines(session, doc_id: int) -> dict:
    """Look up pipeline geometries for the document's unverified place entities.

    Runs after place verification (which handles real point places): a place
    entity the geocoder checked but could NOT confirm may still be linear
    infrastructure — "Baltic Pipe" has no plausible point hit but has an OSM
    route. Only geocoder-rejected entities mentioned at least twice are tried:
    unchecked entities (geocode is None — countries, or verification hasn't
    run) are skipped, so a big document can't flood Overpass with hundreds of
    names. Results, including misses, land in infra_geometries so repeat
    refreshes cost nothing. Queues changes on the session without committing.
    Returns {"checked": int, "resolved": [names]}.
    """
    from library.db.models import DocumentEntity
    from library.place_verification import PLACE_ENTITY_TYPES

    entities = (
        session.query(DocumentEntity)
        .filter(
            DocumentEntity.document_id == doc_id,
            DocumentEntity.entity_type.in_(PLACE_ENTITY_TYPES),
            DocumentEntity.mention_count >= 2,
        )
        .all()
    )

    checked = 0
    resolved: list[str] = []
    for ent in entities:
        if ent.geocode is None or ent.geocode.resolved:
            continue  # unchecked by the geocoder (or a confirmed point place)
        if len(ent.entity_text.strip()) < MIN_QUERY_LENGTH or '"' in ent.entity_text:
            continue
        try:
            row = get_or_fetch_pipeline(session, ent.entity_text)
        except OverpassUnavailable:
            logger.warning("Overpass unavailable — skipping remaining pipeline lookups for doc %s", doc_id)
            break
        checked += 1
        if row.resolved:
            resolved.append(ent.entity_text)

    logger.info("pipeline lookup doc=%s: %d checked, resolved: %s", doc_id, checked, resolved or "-")
    return {"checked": checked, "resolved": resolved}
