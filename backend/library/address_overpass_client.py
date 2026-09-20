"""Manual, bounded OSM address hints; never official registry verification.

Data © OpenStreetMap contributors (ODbL).
"""

import logging
import time

import requests
from unidecode import unidecode

from library.overpass_client import (
    DEFAULT_OVERPASS_URL,
    MIN_REQUEST_INTERVAL_S,
    USER_AGENT,
    OverpassUnavailable,
)

logger = logging.getLogger(__name__)
REQUEST_TIMEOUT_S = 35  # Give the server's 20-second query timeout 15s of headroom.
_last_request_at = 0.0


def _overpass_url() -> str:
    from library.config_loader import load_config
    return (load_config().get("OVERPASS_URL") or DEFAULT_OVERPASS_URL).rstrip("/")


def _fetch_elements(lat: float, lon: float, radius_m: int) -> list[dict]:
    """Mirror the shared Overpass transport convention; failures are not misses."""
    global _last_request_at
    query = (
        '[out:json][timeout:20];\n'
        '(\n'
        f'  node(around:{radius_m},{lat},{lon})["addr:housenumber"];\n'
        f'  way(around:{radius_m},{lat},{lon})["addr:housenumber"];\n'
        ');\n'
        'out center tags;'
    )
    wait = MIN_REQUEST_INTERVAL_S - (time.monotonic() - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    _last_request_at = time.monotonic()

    try:
        from library.external_service_events import observed_request
        response = observed_request(
            service="overpass", operation="address_lookup",
            request_fn=lambda: requests.post(
                _overpass_url(), data={"data": query},
                headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT_S,
            ),
        )
        response.raise_for_status()
        payload = response.json()
        if (not isinstance(payload, dict) or not isinstance(payload.get("elements"), list)
                or payload.get("remark")):
            raise ValueError("Incomplete Overpass response")
        return payload["elements"]
    except requests.RequestException as exc:
        logger.warning("Overpass address request failed: %s", exc)
        raise OverpassUnavailable(str(exc)) from exc
    except ValueError as exc:
        logger.warning("Overpass returned invalid address JSON: %s", exc)
        raise OverpassUnavailable(str(exc)) from exc


def _normalized_street(value: str | None) -> str:
    return unidecode(" ".join((value or "").split())).casefold()


def find_osm_building_match(
    lat: float, lon: float, street: str, building_number: str, radius_m: int = 400,
) -> dict | None:
    """Return an exact building hint and/or a separate same-street postcode hint.

    None means the lookup could not be performed. A neighbor's postcode never
    becomes the matched building's postal_code, even if that tag is missing.
    """
    street_key = _normalized_street(street)
    number_key = (building_number or "").strip().casefold()
    if not street_key or not number_key:
        return None
    try:
        elements = _fetch_elements(lat, lon, radius_m)
    except OverpassUnavailable:
        return None

    match = None
    nearby_postal_code = None
    for element in elements:
        if not isinstance(element, dict):
            continue
        tags = element.get("tags") or {}
        if not isinstance(tags, dict) or not isinstance(tags.get("addr:street"), str):
            continue
        if _normalized_street(tags["addr:street"]) != street_key:
            continue
        number = tags.get("addr:housenumber")
        postal_code = tags.get("addr:postcode")
        if isinstance(number, str) and number.strip().casefold() == number_key:
            if match is None:
                coordinates = element if element.get("type") == "node" else (element.get("center") or {})
                match = {
                    "found": True, "lat": coordinates.get("lat"), "lon": coordinates.get("lon"),
                    "postal_code": postal_code, "housename": tags.get("addr:housename"),
                    "osm_id": element.get("id"), "osm_type": element.get("type"),
                }
        elif nearby_postal_code is None and isinstance(postal_code, str) and postal_code.strip():
            nearby_postal_code = postal_code.strip()

    result = match if match is not None else {"found": False, "postal_code": None}
    result["nearby_postal_code"] = nearby_postal_code if not result["postal_code"] else None
    return result
