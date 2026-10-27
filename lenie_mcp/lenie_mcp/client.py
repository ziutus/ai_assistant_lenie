"""Thin REST client for the Lenie backend. Never exposes the API key in errors."""

from __future__ import annotations

import httpx

from .config import Settings


class LenieError(RuntimeError):
    """Short, key-free error message safe to return to the model."""


class LenieClient:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        self._http = httpx.Client(
            base_url=settings.api_url,
            headers={"x-api-key": settings.api_key},
            timeout=httpx.Timeout(30.0, connect=10.0),
            transport=transport,
        )

    def _request(self, method: str, path: str, **kwargs):
        try:
            resp = self._http.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise LenieError(f"Lenie API unreachable: {type(exc).__name__}") from None
        if resp.status_code >= 400:
            detail = ""
            try:
                body = resp.json()
                detail = str(body.get("message") or body.get("description") or "")[:200]
            except ValueError:
                pass
            raise LenieError(f"Lenie API {method} {path} -> HTTP {resp.status_code} {detail}".strip())
        try:
            return resp.json()
        except ValueError:
            raise LenieError(f"Lenie API {method} {path} returned non-JSON") from None

    def get(self, path: str, **params):
        return self._request("GET", path, params={k: v for k, v in params.items() if v is not None})

    def post(self, path: str, payload: dict):
        return self._request("POST", path, json=payload)
