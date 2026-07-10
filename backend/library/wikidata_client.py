"""Wikidata client for person disambiguation (NER stage 4).

Searches Wikidata for entities matching a person name and keeps only entities
that are actually humans (P31 = Q5) — the drone "Shahed" or a ship named after
a person must not become a Person row. Public API, no key needed; polite
User-Agent per Wikimedia policy. All failures degrade to an empty result:
disambiguation is an enhancement, never a reason to fail a pipeline.

See docs/person-ner-plan.md and docs/ner-integration-plan.md (stage 4).
"""

import logging

import requests

logger = logging.getLogger(__name__)

API_URL = "https://www.wikidata.org/w/api.php"
REQUEST_TIMEOUT_S = 15
USER_AGENT = "lenie-ai/0.3 (https://www.lenie-ai.eu; krzysztof@itsnap.eu) person-ner"

HUMAN_QID = "Q5"
MAX_CANDIDATES = 5


def _get(params: dict) -> dict | None:
    try:
        resp = requests.get(
            API_URL,
            params={**params, "format": "json"},
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT_S,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logger.warning("Wikidata request failed: %s", e)
        return None
    except ValueError as e:
        logger.warning("Wikidata returned invalid JSON: %s", e)
        return None


def _is_human(entity: dict) -> bool:
    claims = entity.get("claims", {}).get("P31", [])
    for claim in claims:
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {})
        if isinstance(value, dict) and value.get("id") == HUMAN_QID:
            return True
    return False


def search_persons(name: str, language: str = "pl") -> list[dict]:
    """Search Wikidata for HUMAN entities matching a name.

    Returns up to MAX_CANDIDATES dicts: {"qid", "label", "description"} —
    description (occupation/known-for) is the context the LLM uses to pick
    the right person. Empty list on miss or any failure.
    """
    if not name or not name.strip():
        return []

    search = _get({
        "action": "wbsearchentities",
        "search": name.strip(),
        "language": language,
        "uselang": language,
        "type": "item",
        "limit": MAX_CANDIDATES * 2,  # some hits will be filtered out as non-human
    })
    if not search:
        return []
    hits = search.get("search", [])
    if not hits:
        return []

    qids = [h["id"] for h in hits if h.get("id")]
    entities = _get({
        "action": "wbgetentities",
        "ids": "|".join(qids),
        "props": "claims",
    })
    if not entities:
        return []
    entity_map = entities.get("entities", {})

    results = []
    for hit in hits:
        qid = hit.get("id")
        if not qid or not _is_human(entity_map.get(qid, {})):
            continue
        results.append({
            "qid": qid,
            "label": hit.get("label") or name,
            "description": hit.get("description") or "",
        })
        if len(results) >= MAX_CANDIDATES:
            break
    return results
