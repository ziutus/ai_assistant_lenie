"""What is left of the OpenRouter API key's spending limit (``GET /api/v1/key``).

The key Lenie uses for completions can carry a spending limit set in the OpenRouter dashboard; the same key
reports ``limit``, ``limit_remaining`` and ``usage`` about itself, so no separate management key is needed.
(Whole-account credits would need ``GET /credits`` with a management key, which is deliberately not used.)
Without a limit on the key OpenRouter reports no remaining amount, only the usage.

The answer is cached for a minute: the page that shows it is opened often and the endpoint is not free of latency.
"""

import logging
import time

import requests

from library.api.openrouter.openrouter_completion import OPENROUTER_BASE_URL
from library.external_service_events import observed_request

logger = logging.getLogger(__name__)

KEY_URL = f"{OPENROUTER_BASE_URL}/key"
REQUEST_TIMEOUT_S = 10
CACHE_TTL_S = 60
LOW_SHARE = 0.2  # amber when this share of the limit or less is left

_cache: dict = {"at": None, "value": None}


def _number(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def interpret_key_data(data: dict) -> dict:
    """The fields the UI needs from the ``data`` object of ``/key``; money in USD, ``None`` when unknown."""
    limit = _number(data.get("limit"))
    remaining = _number(data.get("limit_remaining"))
    has_limit = limit is not None and remaining is not None
    return {
        "status": "ok",
        "has_limit": has_limit,
        "limit_usd": limit,
        "remaining_usd": remaining,
        "usage_usd": _number(data.get("usage")),
        "reset": data.get("limit_reset") if isinstance(data.get("limit_reset"), str) else None,
        "free_tier": bool(data.get("is_free_tier")),
        "low": has_limit and limit > 0 and remaining <= limit * LOW_SHARE,
        "exhausted": has_limit and remaining <= 0,
    }


def _api_key() -> str | None:
    try:
        from library.config_loader import load_config
        return load_config().get("OPENROUTER_API_KEY") or None
    except (Exception, SystemExit):  # config trouble must not break a status read
        return None


def fetch_key_status(use_cache: bool = True) -> dict:
    """``{"status": "ok", ...}`` (see ``interpret_key_data``), ``not_configured`` without a key, else ``unavailable``."""
    now = time.monotonic()
    if use_cache and _cache["at"] is not None and now - _cache["at"] < CACHE_TTL_S:
        return _cache["value"]
    api_key = _api_key()
    if not api_key:
        return {"status": "not_configured"}
    try:
        response = observed_request(
            service="openrouter", operation="key",
            request_fn=lambda: requests.get(
                KEY_URL, headers={"Authorization": f"Bearer {api_key}", "User-Agent": "lenie-server"},
                timeout=REQUEST_TIMEOUT_S,
            ),
        )
        data = response.json().get("data") if response.ok else None
    except (requests.RequestException, ValueError, AttributeError):
        logger.warning("OpenRouter key status request failed", exc_info=True)
        return {"status": "unavailable"}
    if not isinstance(data, dict):
        logger.warning("OpenRouter key status answered HTTP %s without data", response.status_code)
        return {"status": "unavailable"}
    value = interpret_key_data(data)
    _cache.update(at=now, value=value)
    return value
