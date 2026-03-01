"""HTTP client for Lenie backend REST API.

Provides typed methods for each backend endpoint with timeout handling
and user-friendly error messages. Scope: Story 21-2.
"""

import logging

import requests

from src.config import Config

logger = logging.getLogger(__name__)

HTTP_TIMEOUT = 5  # seconds (NFR3)
MAX_ERROR_BODY_LENGTH = 500


# --- Exception hierarchy ---


class ApiError(Exception):
    """Base exception for all API client errors."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class ApiConnectionError(ApiError):
    """Backend unreachable — connection timeout or DNS failure."""


class ApiResponseError(ApiError):
    """Backend returned an error HTTP status code."""

    def __init__(self, message: str, status_code: int, response_body: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


# --- API Client ---


class LenieApiClient:
    """HTTP client for Lenie backend REST API."""

    def __init__(self, base_url: str, api_key: str):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._session = requests.Session()
        self._session.headers.update({
            "x-api-key": self._api_key,
            "Content-Type": "application/json",
        })

    def _request(self, method: str, path: str, **kwargs) -> dict:
        url = f"{self._base_url}{path}"
        try:
            resp = self._session.request(method, url, timeout=HTTP_TIMEOUT, **kwargs)
        except requests.ConnectionError as exc:
            raise ApiConnectionError(f"Cannot connect to backend at {self._base_url}: {exc}") from exc
        except requests.Timeout as exc:
            raise ApiConnectionError(f"Backend request timed out ({HTTP_TIMEOUT}s): {path}") from exc
        except requests.RequestException as exc:
            raise ApiConnectionError(f"Request failed for {path}: {exc}") from exc

        if resp.status_code >= 400:
            raise ApiResponseError(
                f"Backend returned HTTP {resp.status_code} for {path}",
                status_code=resp.status_code,
                response_body=resp.text[:MAX_ERROR_BODY_LENGTH],
            )

        try:
            return resp.json()
        except (ValueError, requests.exceptions.JSONDecodeError) as exc:
            raise ApiResponseError(
                f"Backend returned non-JSON response for {path}",
                status_code=resp.status_code,
                response_body=resp.text[:MAX_ERROR_BODY_LENGTH],
            ) from exc

    def get_version(self) -> dict:
        """GET /version — returns backend version info."""
        return self._request("GET", "/version")

    def add_url(self, url: str, url_type: str = "link", **kwargs) -> dict:
        """POST /url_add — submit a URL to the knowledge base."""
        payload = {"url": url, "type": url_type, **kwargs}
        return self._request("POST", "/url_add", json=payload)

    def get_document(self, document_id: int) -> dict:
        """GET /website_get?id={document_id} — fetch a single document."""
        return self._request("GET", "/website_get", params={"id": document_id})

    def get_count(self, document_type: str = "ALL") -> int:
        """GET /website_list?type={document_type} — returns total document count."""
        data = self._request("GET", "/website_list", params={"type": document_type})
        if "all_results_count" not in data:
            raise ApiResponseError(
                "Unexpected response format: missing 'all_results_count'",
                status_code=200,
                response_body=str(data)[:MAX_ERROR_BODY_LENGTH],
            )
        return data["all_results_count"]

    def check_url(self, url: str) -> dict | None:
        """GET /website_list?search_in_document={url} — returns first match or None."""
        data = self._request("GET", "/website_list", params={"search_in_document": url})
        websites = data.get("websites", [])
        return websites[0] if websites else None


# --- Factory ---


def create_client(cfg: Config) -> LenieApiClient:
    """Create a configured LenieApiClient from application config."""
    base_url = cfg.require("LENIE_API_URL", "http://lenie-ai-server:5000")
    api_key = cfg.require("STALKER_API_KEY")
    logger.info("API client configured for %s", base_url)
    return LenieApiClient(base_url=base_url, api_key=api_key)
