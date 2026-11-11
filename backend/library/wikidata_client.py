"""Wikidata client for person disambiguation (NER stage 4).

Searches Wikidata for entities matching a person name and keeps only entities
that are actually humans (P31 = Q5) — the drone "Shahed" or a ship named after
a person must not become a Person row. Public API, no key needed; polite
User-Agent per Wikimedia policy. All failures degrade to an empty result:
disambiguation is an enhancement, never a reason to fail a pipeline.

See docs/person-ner-plan.md and docs/ner-integration-plan.md (stage 4).
"""

import logging
import re
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

API_URL = "https://www.wikidata.org/w/api.php"
REQUEST_TIMEOUT_S = 15
USER_AGENT = "lenie-ai/0.3 (https://www.lenie-ai.eu; krzysztof@itsnap.eu) person-ner"

HUMAN_QID = "Q5"
MAX_CANDIDATES = 5

# Wikipedia editions tried in order when a QID has several sitelinks (Polish first - the reader is Polish).
WIKIPEDIA_SITES = ("plwiki", "enwiki")
_WIKIPEDIA_HOST = re.compile(r"[a-z]{2,3}(?:-[a-z]{2,8})?(?:\.m)?\.wikipedia\.org")


def normalize_wikipedia_url(raw) -> str | None:
    """Validate a Wikipedia article address; empty -> None. Raises ValueError with a Polish message.

    Only ``http(s)://<lang>.wikipedia.org/wiki/<title>`` is accepted (checked on the parsed host, not by
    substring), and the result is always https.
    """
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ValueError("Adres Wikipedii musi być tekstem.")
    url = raw.strip()
    if not url:
        return None
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if (parsed.scheme not in ("http", "https") or not _WIKIPEDIA_HOST.fullmatch(host)
            or not parsed.path.startswith("/wiki/") or len(parsed.path) <= len("/wiki/") or len(url) > 500):
        raise ValueError("Adres Wikipedii ma postać https://pl.wikipedia.org/wiki/Tytuł.")
    return parsed._replace(scheme="https", fragment="").geturl()


def _wikipedia_url_from_entity(entity: dict) -> str | None:
    sitelinks = entity.get("sitelinks") or {}
    for site in WIKIPEDIA_SITES:
        url = (sitelinks.get(site) or {}).get("url")
        if url:
            try:
                return normalize_wikipedia_url(url)
            except ValueError:
                continue
    return None


def wikipedia_urls_for_qids(qids: list[str]) -> dict[str, str]:
    """{qid: Wikipedia article URL} for the QIDs that have a pl/en article (one batched request per 50).

    Missing articles and any failure simply leave the QID out - the address is an enhancement."""
    result: dict[str, str] = {}
    unique = [q for q in dict.fromkeys(qids) if re.fullmatch(r"Q\d{1,12}", q or "")]
    for start in range(0, len(unique), 50):
        batch = unique[start:start + 50]
        data = _get({"action": "wbgetentities", "ids": "|".join(batch), "props": "sitelinks/urls",
                     "sitefilter": "|".join(WIKIPEDIA_SITES)})
        for qid, entity in ((data or {}).get("entities") or {}).items():
            url = _wikipedia_url_from_entity(entity) if isinstance(entity, dict) else None
            if url:
                result[qid] = url
    return result


def wikipedia_url_for_qid(qid: str) -> str | None:
    return wikipedia_urls_for_qids([qid]).get(qid)


def _get(params: dict) -> dict | None:
    try:
        from library.external_service_events import observed_request
        resp = observed_request(
            service="wikidata", operation=str(params.get("action") or "request"),
            request_fn=lambda: requests.get(
                API_URL,
                params={**params, "format": "json"},
                headers={"User-Agent": USER_AGENT},
                timeout=REQUEST_TIMEOUT_S,
            ),
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
        "props": "labels|descriptions|sitelinks/urls",
        "sitefilter": "|".join(WIKIPEDIA_SITES),
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
        results.append({"qid": qid, "label": label, "description": description,
                        "wikipedia_url": _wikipedia_url_from_entity(entity)})
    return results
