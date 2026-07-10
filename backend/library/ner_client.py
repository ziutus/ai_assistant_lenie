"""HTTP client for the internal NER microservice (ner_service/, spaCy pl_core_news_lg).

Service URL comes from config (NER_SERVICE_URL), default matches the container
name on the Docker network. The service is internal-only (no auth) — see
ner_service/README.md. All failures degrade to an empty result with a warning:
entity extraction is an enhancement, never a reason to fail a pipeline.

Integration plan: docs/ner-integration-plan.md.
"""

import logging
from collections import Counter

import requests

logger = logging.getLogger(__name__)

DEFAULT_NER_SERVICE_URL = "http://lenie-ner-service:8090"

# Entity labels we persist (pl_core_news_lg also emits orgName, date, time, ...)
ENTITY_TYPES = ("persName", "geogName", "placeName")

# First /ner call after a container restart loads the model (up to ~90s on the
# NAS Celeron — see ner_service/README.md); later calls are sub-second.
REQUEST_TIMEOUT_S = 120

# Keep requests to the CPU-only service bounded (spaCy's own limit is 1M chars).
MAX_TEXT_CHARS = 200_000


def _service_url() -> str:
    from library.config_loader import load_config
    return (load_config().get("NER_SERVICE_URL") or DEFAULT_NER_SERVICE_URL).rstrip("/")


def extract_entities(text: str) -> list[dict]:
    """Return raw entities from the NER service: [{text, label, lemma, start, end}, ...].

    Empty list on any failure (service down, timeout, bad response) — callers
    must treat "no entities" and "service unavailable" the same way.
    """
    if not text or not text.strip():
        return []
    try:
        resp = requests.post(
            f"{_service_url()}/ner",
            json={"text": text[:MAX_TEXT_CHARS]},
            timeout=REQUEST_TIMEOUT_S,
        )
        resp.raise_for_status()
        entities = resp.json().get("entities", [])
        if not isinstance(entities, list):
            logger.warning("NER service returned unexpected payload shape")
            return []
        return entities
    except requests.RequestException as e:
        logger.warning("NER service unavailable (%s): %s", _service_url(), e)
        return []
    except ValueError as e:
        logger.warning("NER service returned invalid JSON: %s", e)
        return []


def warmup_async() -> None:
    """Fire-and-forget /ner probe in a daemon thread to pre-load the spaCy model.

    Call at the start of scripts that will use NER later (article_browser,
    youtube analysis): the one-time model load (~90s on the NAS after a
    container restart) then overlaps with S3 downloads / LLM calls instead of
    stalling the first real extraction. Errors are ignored — warmup must be
    invisible when the service is down.
    """
    import threading

    def _probe() -> None:
        try:
            requests.post(f"{_service_url()}/ner", json={"text": "ping"}, timeout=REQUEST_TIMEOUT_S)
        except Exception:
            logger.debug("NER warmup probe failed (ignored)")

    threading.Thread(target=_probe, name="ner-warmup", daemon=True).start()


def aggregate_entities(entities: list[dict], types: tuple[str, ...] = ENTITY_TYPES) -> dict[tuple[str, str], int]:
    """Group raw mentions by (entity_type, base form) with occurrence counts.

    The base form is the lemma when the service provides one (groups Polish
    inflected variants: "Tuska" -> "Tusk"), falling back to the surface text.
    """
    counts: Counter[tuple[str, str]] = Counter()
    for ent in entities:
        label = ent.get("label")
        if label not in types:
            continue
        base = (ent.get("lemma") or ent.get("text") or "").strip()
        if not base:
            continue
        counts[(label, base)] += 1
    return dict(counts)
