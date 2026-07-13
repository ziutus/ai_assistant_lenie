"""HTTP client for the internal NER microservice (ner_service/, spaCy pl_core_news_lg).

Service URL comes from config (NER_SERVICE_URL), default matches the container
name on the Docker network. The service is internal-only (no auth) — see
ner_service/README.md. All failures degrade to an empty result with a warning:
entity extraction is an enhancement, never a reason to fail a pipeline.

Integration plan: docs/ner-integration-plan.md.
"""

import logging
import re
from collections import Counter

import requests

from library.ner_normalization import (
    canonical_country_for_surface,
    is_rejected_surface_lemma_pair,
    normalize_ner_text,
)

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


class NERExtractionError(RuntimeError):
    """A complete NER extraction could not be obtained."""


def _extract_entities(text: str, *, strict: bool) -> list[dict]:
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
    for window_index, window in enumerate(_iter_windows(text), start=1):
        try:
            resp = requests.post(
                f"{_service_url()}/ner",
                json={"text": window},
                timeout=REQUEST_TIMEOUT_S,
            )
            resp.raise_for_status()
            entities = resp.json().get("entities", [])
            if not isinstance(entities, list):
                raise ValueError("NER service returned unexpected payload shape")
            collected.extend(entities)
        except (requests.RequestException, ValueError) as exc:
            message = f"NER extraction failed in window {window_index}: {exc}"
            if strict:
                raise NERExtractionError(message) from exc
            logger.warning(message)
            break
    return collected


def extract_entities(text: str) -> list[dict]:
    """Best-effort extraction; preserves partial-result legacy behavior."""
    return _extract_entities(text, strict=False)


def extract_entities_strict(text: str) -> list[dict]:
    """Return only a complete extraction; raise on failure of any text window."""
    return _extract_entities(text, strict=True)


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


def _is_initials_only(surface: str) -> bool:
    tokens = surface.split()
    return bool(tokens) and all(
        re.fullmatch(r"[^\W\d_]\.", token, re.UNICODE) and token[0].isupper()
        for token in tokens
    )


def _preferred_spelling(spellings: Counter[str], order: list[str]) -> str:
    """Pick the most frequent capitalized spelling, with first-seen tie breaks."""
    capitalized = [value for value in order if value and value[0].isupper()]
    candidates = capitalized or order
    return max(candidates, key=lambda value: (spellings[value], -order.index(value)))


def _deduplicated_spellings(spellings: Counter[str], order: list[str]) -> list[str]:
    """Collapse case-only variants while preserving first-seen key order."""
    buckets: dict[str, Counter[str]] = {}
    bucket_order: list[str] = []
    spelling_order: dict[str, list[str]] = {}
    for value in order:
        key = value.casefold()
        if key not in buckets:
            buckets[key] = Counter()
            spelling_order[key] = []
            bucket_order.append(key)
        if value not in spelling_order[key]:
            spelling_order[key].append(value)
        buckets[key][value] += spellings[value]
    return [_preferred_spelling(buckets[key], spelling_order[key]) for key in bucket_order]


def _is_truncated_lemma(base: str, variants: list[str]) -> bool:
    """Detect spaCy lemmas such as Brn/Wiln/Wegr cut from every full surface."""
    base_key = base.casefold()
    return bool(variants) and all(
        variant.casefold().startswith(base_key)
        and variant.casefold() != base_key
        and len(variant) - len(base) >= 2
        for variant in variants
    )


def aggregate_entities_detailed(
    entities: list[dict], types: tuple[str, ...] = ENTITY_TYPES,
) -> dict[tuple[str, str], dict]:
    """Normalize and group raw mentions into stable person/place entities.

    New ner_service payloads are filtered by root-token POS; payloads without
    POS retain legacy behavior. Country names, selected demonyms and exact
    uppercase abbreviations are canonicalized. Case-only duplicates share one
    display spelling, and geogName/placeName duplicates share the more frequent
    label. Suspicious cut-off lemmas fall back to their best full surface form.

    Shape: {(entity_type, base): {"count", "variants", "raw_lemmas"}}.
    raw_lemmas is internal metadata used to preserve ner_exclusions behavior
    after canonicalization; it is not persisted or returned by the API.
    """
    preliminary: dict[tuple[str, str], dict] = {}
    for ent in entities:
        label = ent.get("label")
        if label not in types:
            continue
        surface = normalize_ner_text(ent.get("text") or "")
        if not surface or _is_initials_only(surface):
            continue
        if surface[0].islower():
            continue
        lemma = normalize_ner_text(ent.get("lemma") or surface)
        if not lemma:
            continue

        pos = normalize_ner_text(ent.get("pos") or "").upper() or None
        if pos is not None and pos not in {"NOUN", "PROPN"}:
            continue
        if is_rejected_surface_lemma_pair(surface, lemma, pos):
            continue

        country = canonical_country_for_surface(surface) if label in {"geogName", "placeName"} else None
        base = country or lemma
        key = (label, base.casefold())
        group = preliminary.setdefault(
            key,
            {
                "count": 0,
                "base_spellings": Counter(),
                "base_order": [],
                "surface_spellings": Counter(),
                "surface_order": [],
                "raw_lemma_spellings": Counter(),
                "raw_lemma_order": [],
            },
        )
        group["count"] += 1
        for value, counter_name, order_name in (
            (base, "base_spellings", "base_order"),
            (surface, "surface_spellings", "surface_order"),
            (lemma, "raw_lemma_spellings", "raw_lemma_order"),
        ):
            group[counter_name][value] += 1
            if value not in group[order_name]:
                group[order_name].append(value)

    normalized_groups: list[dict] = []
    for (label, _base_key), group in preliminary.items():
        base = _preferred_spelling(group["base_spellings"], group["base_order"])
        variants = _deduplicated_spellings(group["surface_spellings"], group["surface_order"])
        if _is_truncated_lemma(base, variants):
            base = _preferred_spelling(group["surface_spellings"], group["surface_order"])
        normalized_groups.append({"label": label, "base": base, "variants": variants, **group})

    merged: dict[tuple[str, str], dict] = {}
    for source in normalized_groups:
        family = "persName" if source["label"] == "persName" else "place"
        key = (family, source["base"].casefold())
        group = merged.setdefault(
            key,
            {
                "count": 0,
                "label_counts": Counter(),
                "label_order": [],
                "base_spellings": Counter(),
                "base_order": [],
                "surface_spellings": Counter(),
                "surface_order": [],
                "raw_lemma_spellings": Counter(),
                "raw_lemma_order": [],
            },
        )
        group["count"] += source["count"]
        group["label_counts"][source["label"]] += source["count"]
        if source["label"] not in group["label_order"]:
            group["label_order"].append(source["label"])
        group["base_spellings"][source["base"]] += source["count"]
        if source["base"] not in group["base_order"]:
            group["base_order"].append(source["base"])
        for value, counter_name, order_name in (
            *[(value, "surface_spellings", "surface_order") for value in source["surface_order"]],
            *[(value, "raw_lemma_spellings", "raw_lemma_order") for value in source["raw_lemma_order"]],
        ):
            source_counter = source[counter_name]
            group[counter_name][value] += source_counter[value]
            if value not in group[order_name]:
                group[order_name].append(value)

    result: dict[tuple[str, str], dict] = {}
    for group in merged.values():
        label = max(
            group["label_order"],
            key=lambda value: (group["label_counts"][value], -group["label_order"].index(value)),
        )
        base = _preferred_spelling(group["base_spellings"], group["base_order"])
        result[(label, base)] = {
            "count": group["count"],
            "variants": _deduplicated_spellings(group["surface_spellings"], group["surface_order"]),
            "raw_lemmas": _deduplicated_spellings(
                group["raw_lemma_spellings"], group["raw_lemma_order"],
            ),
        }
    return result


def aggregate_entities(entities: list[dict], types: tuple[str, ...] = ENTITY_TYPES) -> dict[tuple[str, str], int]:
    """Group raw mentions by (entity_type, base form) with occurrence counts.

    Counts-only view of aggregate_entities_detailed() — see there for the
    grouping and filtering rules.
    """
    return {key: group["count"] for key, group in aggregate_entities_detailed(entities, types).items()}
