"""Manual address matching via adresy.app, a third-party PRG aggregator.

GET response contract: https://adresy.app/api/ (checked 2026-09-20).
The live endpoint was unreachable from the development sandbox; fixtures use
the documented shape. No cache, retries or automatic/bulk verification.
"""

import logging

import requests

logger = logging.getLogger(__name__)

MATCH_URL = "https://api.adresy.app/api/v1/match"
REQUEST_TIMEOUT_S = 15


def _api_key() -> str | None:
    from library.config_loader import load_config
    return load_config().get("ADRESY_APP_API_KEY")


def validate_address_external(query: str) -> dict | None:
    """Return {outcome: confirmed, match: dict}, {outcome: not_found}, or None.

    None means no conclusive answer: HTTP/network/JSON failure, unexpected
    payload or the documented ambiguous status. Only explicit not_found or
    an empty results list is a registry miss. An API key is optional.
    """
    try:
        from library.external_service_events import observed_request
        key = _api_key()
        response = observed_request(
            service="adresy_app", operation="match",
            request_fn=lambda: requests.get(
                MATCH_URL, params={"q": query},
                headers={"X-API-Key": key} if key else {},
                timeout=REQUEST_TIMEOUT_S,
            ),
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        logger.warning("Adresy.app request failed: %s", type(exc).__name__)
        return None
    except ValueError:
        logger.warning("Adresy.app returned invalid JSON")
        return None

    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        return None
    results = payload["results"]
    if not results:
        return {"outcome": "not_found"}
    if len(results) != 1 or not isinstance(results[0], dict):
        return None
    result = results[0]
    match = result.get("match")
    if result.get("status") == "not_found" and not match:
        return {"outcome": "not_found"}
    if result.get("status") == "matched" and isinstance(match, dict) and match:
        return {"outcome": "confirmed", "match": match}
    return None
