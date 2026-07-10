"""LocationIQ geocoding client with match-quality checking (NER stage 3).

Verifies that a name detected by NER is a real geographic place. A bare
geocoder hit is NOT proof: rare Polish exonyms fuzzy-match to wrong places
(live test 2026-07-09: "Cieśnina Ormuz" returned "Płytka Cieśnina" near Iława),
so every hit goes through is_plausible_match() before it counts as resolved.

Free tier limits: 5000 req/day, 2 req/s — callers cache results in
geocode_cache (library/place_verification.py) and this module sleeps between
consecutive requests. API key from config (LOCATIONIQ_API_KEY, in Vault).
"""

import logging
import time
import unicodedata
from difflib import SequenceMatcher

import requests

logger = logging.getLogger(__name__)

SEARCH_URL = "https://us1.locationiq.com/v1/search"
REQUEST_TIMEOUT_S = 15

# Free tier: 2 req/s. 0.6s spacing keeps a safety margin.
MIN_REQUEST_INTERVAL_S = 0.6
_last_request_at = 0.0

# Minimal similarity between the query and the best token run of display_name
# for a hit to count as the place we asked about ("Cieśnina Ormuz" vs
# "Płytka Cieśnina, Iława" scores well below this).
MIN_NAME_SIMILARITY = 0.75


def _api_key() -> str | None:
    from library.config_loader import load_config
    return load_config().get("LOCATIONIQ_API_KEY")


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def _name_similarity(query: str, display_name: str) -> float:
    """Best fuzzy similarity between the query and any comma-separated part of display_name.

    display_name is hierarchical ("Kyiv, Ukraine"); the queried place is one of
    its parts, usually the first. Accents are stripped so "Kijow"/"Kijów"
    variants compare equal.
    """
    q = _strip_accents(query.lower().strip())
    best = 0.0
    for part in display_name.split(","):
        p = _strip_accents(part.lower().strip())
        if not p:
            continue
        best = max(best, SequenceMatcher(None, q, p).ratio())
    return best


def is_plausible_match(query: str, hit: dict) -> bool:
    """Does the geocoder hit plausibly refer to the queried place name?

    Guards against fuzzy false positives. Note this can't catch a *different
    real place with the same name* (that disambiguation is the LLM's job in
    place_verification); it only rejects hits whose name doesn't match what
    was asked.
    """
    display_name = hit.get("display_name") or ""
    if not display_name:
        return False
    return _name_similarity(query, display_name) >= MIN_NAME_SIMILARITY


def geocode(query: str) -> dict | None:
    """Geocode a place name. Returns the raw first hit, or None on miss/failure.

    Rate-limited to the free-tier request spacing. Callers must cache results
    (geocode_cache) — this function performs a live API call every time.
    """
    global _last_request_at

    key = _api_key()
    if not key:
        logger.warning("LOCATIONIQ_API_KEY not configured — place verification disabled")
        return None

    wait = MIN_REQUEST_INTERVAL_S - (time.monotonic() - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    _last_request_at = time.monotonic()

    try:
        resp = requests.get(
            SEARCH_URL,
            params={"key": key, "q": query, "format": "json", "limit": 1},
            timeout=REQUEST_TIMEOUT_S,
        )
        if resp.status_code == 404:
            # LocationIQ returns 404 "Unable to geocode" for a clean miss
            return None
        resp.raise_for_status()
        hits = resp.json()
        return hits[0] if isinstance(hits, list) and hits else None
    except requests.RequestException as e:
        logger.warning("LocationIQ request failed for %r: %s", query, e)
        return None
    except ValueError as e:
        logger.warning("LocationIQ returned invalid JSON for %r: %s", query, e)
        return None
