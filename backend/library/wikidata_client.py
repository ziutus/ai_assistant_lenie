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


def _text_in_language(values: dict, language: str) -> str:
    for lang in (language, "en"):
        entry = values.get(lang)
        if entry and entry.get("value"):
            return entry["value"]
    return ""


def search_persons(name: str, language: str = "pl") -> list[dict]:
    """Search Wikidata for HUMAN entities matching a name.

    Uses fulltext search (CirrusSearch) with the haswbstatement:P31=Q5 filter
    instead of wbsearchentities — the latter only matches labels/aliases, so a
    bare famous surname ("Trump") missed the intended person entirely (found
    only a namesake gamer; live E2E 2026-07-10). Fulltext ranks Donald Trump
    first for "Trump".

    Returns up to MAX_CANDIDATES dicts: {"qid", "label", "description"} —
    description (occupation/known-for) is the context the LLM uses to pick
    the right person. Empty list on miss or any failure.
    """
    if not name or not name.strip():
        return []

    search = _get({
        "action": "query",
        "list": "search",
        "srsearch": f"{name.strip()} haswbstatement:P31={HUMAN_QID}",
        "srlimit": MAX_CANDIDATES,
    })
    if not search:
        return []
    qids = [
        h["title"] for h in search.get("query", {}).get("search", [])
        if h.get("title", "").startswith("Q")
    ]
    if not qids:
        return []

    entities = _get({
        "action": "wbgetentities",
        "ids": "|".join(qids),
        "props": "labels|descriptions",
        "languages": f"{language}|en",
    })
    if not entities:
        return []
    entity_map = entities.get("entities", {})

    results = []
    for qid in qids:
        entity = entity_map.get(qid, {})
        label = _text_in_language(entity.get("labels", {}), language) or name
        description = _text_in_language(entity.get("descriptions", {}), language)
        results.append({"qid": qid, "label": label, "description": description})
    return results
