"""OpenRouter model catalog: live prices and limits from the public ``GET /api/v1/models`` endpoint.

The endpoint needs no API key and sends no document text, so reading it is allowed even while
``OPENROUTER_ENABLED`` is off. Prices come back as USD-per-token strings; they are converted to
Decimal USD per million tokens and never pass through float. The catalog is cached in the process and
every failure degrades to "unknown" — a price lookup must never break an LLM call or a page.
"""

import logging
import threading
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

import requests

from library.api.openrouter.openrouter_completion import OPENROUTER_BASE_URL

logger = logging.getLogger(__name__)

CATALOG_URL = f"{OPENROUTER_BASE_URL}/models"
CATALOG_TTL_SECONDS = 6 * 3600
FAILURE_BACKOFF_SECONDS = 120
REQUEST_TIMEOUT_SECONDS = 5
CURRENCY = "USD"
_PER_MILLION = Decimal(1_000_000)
_PRICE_SCALE = Decimal("0.000001")  # llm_pricing.*_price_per_million is NUMERIC(12, 6)


@dataclass(frozen=True)
class OpenRouterModelInfo:
    id: str
    context_length: int | None
    max_completion_tokens: int | None
    input_price_per_million: Decimal | None
    output_price_per_million: Decimal | None
    supports_structured_outputs: bool
    currency: str = CURRENCY


_lock = threading.Lock()
_catalog: dict[str, OpenRouterModelInfo] = {}
_loaded_at: float | None = None
_failed_at: float | None = None


def _price_per_million(value) -> Decimal | None:
    """USD-per-token string -> USD per million tokens; None for missing or negative (-1 = router, no fixed price)."""
    if value is None:
        return None
    try:
        per_token = Decimal(str(value))
    except InvalidOperation:
        return None
    if per_token < 0:
        return None
    return (per_token * _PER_MILLION).quantize(_PRICE_SCALE)


def _positive_int(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def parse_catalog(payload: dict) -> dict[str, OpenRouterModelInfo]:
    """``{id: OpenRouterModelInfo}`` from a ``/models`` response body; malformed entries are skipped."""
    catalog: dict[str, OpenRouterModelInfo] = {}
    for item in (payload or {}).get("data") or []:
        model_id = item.get("id") if isinstance(item, dict) else None
        if not isinstance(model_id, str) or not model_id:
            continue
        pricing = item.get("pricing") or {}
        top_provider = item.get("top_provider") or {}
        catalog[model_id] = OpenRouterModelInfo(
            id=model_id,
            context_length=_positive_int(item.get("context_length")),
            max_completion_tokens=_positive_int(top_provider.get("max_completion_tokens")),
            input_price_per_million=_price_per_million(pricing.get("prompt")),
            output_price_per_million=_price_per_million(pricing.get("completion")),
            supports_structured_outputs="structured_outputs" in (item.get("supported_parameters") or []),
        )
    return catalog


def _fetch() -> dict[str, OpenRouterModelInfo]:
    response = requests.get(CATALOG_URL, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return parse_catalog(response.json())


def get_catalog(*, refresh: bool = False) -> dict[str, OpenRouterModelInfo]:
    """The cached catalog; empty when it was never loaded and OpenRouter is unreachable.

    A stale catalog is kept when a refresh fails, and a failed fetch is not retried for
    ``FAILURE_BACKOFF_SECONDS`` so an outage costs at most one short timeout per window.
    """
    global _catalog, _loaded_at, _failed_at
    now = time.monotonic()
    with _lock:
        fresh = _loaded_at is not None and now - _loaded_at < CATALOG_TTL_SECONDS
        backing_off = _failed_at is not None and now - _failed_at < FAILURE_BACKOFF_SECONDS
        if (fresh and not refresh) or (backing_off and not refresh):
            return _catalog
        try:
            loaded = _fetch()
        except Exception as exc:
            _failed_at = now
            logger.warning("OpenRouter catalog fetch failed: %s", type(exc).__name__)
            return _catalog
        if loaded:
            _catalog, _loaded_at, _failed_at = loaded, now, None
        else:
            _failed_at = now
        return _catalog


def get_model_info(openrouter_id: str) -> OpenRouterModelInfo | None:
    """Catalog entry for an OpenRouter id (without the internal ``openrouter/`` prefix), else None."""
    return get_catalog().get(openrouter_id)


def reset_cache() -> None:
    """Forget the cached catalog (tests)."""
    global _catalog, _loaded_at, _failed_at
    with _lock:
        _catalog, _loaded_at, _failed_at = {}, None, None
