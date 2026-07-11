"""HTTP client for the internal NER microservice (ner_service/, spaCy pl_core_news_lg).

Service URL comes from config (NER_SERVICE_URL), default matches the container
name on the Docker network. The service is internal-only (no auth) — see
ner_service/README.md. All failures degrade to an empty result with a warning:
entity extraction is an enhancement, never a reason to fail a pipeline.

Integration plan: docs/ner-integration-plan.md.
"""

import logging

import requests

logger = logging.getLogger(__name__)

DEFAULT_NER_SERVICE_URL = "http://lenie-ner-service:8090"

# Entity labels we persist (pl_core_news_lg also emits orgName, date, time, ...)
ENTITY_TYPES = ("persName", "geogName", "placeName")

# First /ner call after a container restart loads the model (up to ~90s on the
# NAS Celeron — see ner_service/README.md); later calls are sub-second.
REQUEST_TIMEOUT_S = 120

# Keep single requests to the CPU-only service bounded (spaCy's own limit is
# 1M chars). Longer texts are extracted in windows of this size — see
# _iter_windows(); a 1.5M-char book used to be silently truncated to the
# first window, so persons unique to late chapters never became entities.
MAX_TEXT_CHARS = 200_000

# Total cap across all windows — bounds worst-case NER time on the NAS Celeron
# (~1-2 min per window) for pathologically long inputs.
MAX_TEXT_TOTAL = 2_000_000

# When cutting a window, back up to the nearest whitespace within this many
# chars so a name straddling the boundary isn't split in half.
WINDOW_BOUNDARY_BACKTRACK = 200


def _service_url() -> str:
    from library.config_loader import load_config
    return (load_config().get("NER_SERVICE_URL") or DEFAULT_NER_SERVICE_URL).rstrip("/")


def _iter_windows(text: str, size: int = MAX_TEXT_CHARS, total_cap: int = MAX_TEXT_TOTAL):
    """Yield consecutive windows of at most `size` chars, cut at whitespace.

    The cut backs up to the nearest whitespace within WINDOW_BOUNDARY_BACKTRACK
    chars so a name straddling the boundary isn't split. Text beyond
    `total_cap` is dropped.
    """
    text = text[:total_cap]
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            floor = max(start, end - WINDOW_BOUNDARY_BACKTRACK)
            ws = max(text.rfind(" ", floor, end), text.rfind("\n", floor, end))
            if ws > start:
                end = ws
        yield text[start:end]
        start = end


def extract_entities(text: str) -> list[dict]:
    """Return raw entities from the NER service: [{text, label, lemma, start, end}, ...].

    Long texts are processed in windows (see _iter_windows) and the mentions
    concatenated — note start/end offsets are window-relative, not absolute;
    the aggregation path ignores them. Empty list on total failure (service
    down, timeout, bad response) — callers must treat "no entities" and
    "service unavailable" the same way. When a later window fails, the
    mentions collected so far are returned (partial coverage beats none) and
    remaining windows are skipped to avoid hammering a failing service.
    """
    if not text or not text.strip():
        return []
    collected: list[dict] = []
    for window in _iter_windows(text):
        try:
            resp = requests.post(
                f"{_service_url()}/ner",
                json={"text": window},
                timeout=REQUEST_TIMEOUT_S,
            )
            resp.raise_for_status()
            entities = resp.json().get("entities", [])
            if not isinstance(entities, list):
                logger.warning("NER service returned unexpected payload shape")
                break
            collected.extend(entities)
        except requests.RequestException as e:
            logger.warning("NER service unavailable (%s): %s", _service_url(), e)
            break
        except ValueError as e:
            logger.warning("NER service returned invalid JSON: %s", e)
            break
    return collected


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


def aggregate_entities_detailed(
    entities: list[dict], types: tuple[str, ...] = ENTITY_TYPES,
) -> dict[tuple[str, str], dict]:
    """Group raw mentions by (entity_type, base form): occurrence counts + surface variants.

    The base form is the lemma when the service provides one (groups Polish
    inflected variants: "Tuska" -> "Tusk"), falling back to the surface text.
    Each group also collects its distinct surface forms in first-seen order
    ("Kijów", "Kijowa") — the chapter-scoped entity filter matches on them,
    since the lemma itself may never appear in the text.

    Mentions whose surface text starts lowercase are dropped: Polish proper
    names are capitalized, so a lowercase mention is an adjective/demonym the
    model mislabeled as a place ("ukraiński", "rosyjski"). The check uses the
    surface text, not the lemma — legitimate lemmas can start lowercase
    ("Cieśninie Ormuz" -> "cieśnina Ormuz").

    Shape: {(entity_type, base): {"count": int, "variants": [surface, ...]}}.
    """
    groups: dict[tuple[str, str], dict] = {}
    for ent in entities:
        label = ent.get("label")
        if label not in types:
            continue
        surface = (ent.get("text") or "").strip()
        if not surface or surface[0].islower():
            continue
        base = (ent.get("lemma") or surface).strip()
        if not base:
            continue
        group = groups.setdefault((label, base), {"count": 0, "variants": []})
        group["count"] += 1
        if surface not in group["variants"]:
            group["variants"].append(surface)
    return groups


def aggregate_entities(entities: list[dict], types: tuple[str, ...] = ENTITY_TYPES) -> dict[tuple[str, str], int]:
    """Group raw mentions by (entity_type, base form) with occurrence counts.

    Counts-only view of aggregate_entities_detailed() — see there for the
    grouping and filtering rules.
    """
    return {key: group["count"] for key, group in aggregate_entities_detailed(entities, types).items()}
