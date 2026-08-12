"""Resolve newsletter tracking links without allowing redirects to internal hosts."""

import base64
import logging
import re
from urllib.parse import urlparse

import requests

from library.url_normalization import canonicalize_url
from library.website.website_download_context import validate_url_target

logger = logging.getLogger(__name__)

_TRACKING_HOST_PATTERNS = (
    # ESP hostnames can contain hyphens, e.g. ``30e6d271.click.kit-mail3.com``.
    r"(?:^|\.)click\.[a-z0-9-]+(?:\.[a-z0-9-]+)+$",
    r"(?:^|\.)links\.[a-z0-9-]+(?:\.[a-z0-9-]+)+$",
    r"(?:^|\.)track\.[a-z0-9-]+(?:\.[a-z0-9-]+)+$",
    r"(?:^|\.)email\.mg\.[a-z0-9-]+$",
    r"(?:^|\.)u\d+\.ct\.sendgrid\.net$",
    r"(?:^|\.)r\.email\.[a-z0-9-]+$",
    r"(?:^|\.)mandrillapp\.com$",
    r"(?:^|\.)emlnk\d*\.com$",
)

# Plain-text email imports preserve links as ``etykieta (https://...)``.  Keep
# the matcher deliberately conservative: closing punctuation belongs to prose,
# not the URL, and is reattached after a replacement.
_TEXT_URL_RE = re.compile(r"https?://[^\s<>\"']+")
_TRAILING_URL_PUNCTUATION = ".,;:!?)]}"


def is_tracking_url(url: str) -> bool:
    """Return whether *url* belongs to a known newsletter redirect service."""
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    path_and_query = parsed.path + (f"?{parsed.query}" if parsed.query else "")
    return bool(
        hostname and any(re.search(pattern, hostname) for pattern in _TRACKING_HOST_PATTERNS)
        or re.search(r"/lt\.php\?", path_and_query)
    )


def _embedded_destination(url: str) -> str | None:
    """Return a URL encoded as the last path component by some ESPs.

    Kit uses URL-safe Base64 for the destination.  Decoding it avoids a
    network request while retaining the ordinary redirect resolver for other
    providers.
    """
    token = urlparse(url).path.rsplit("/", 1)[-1]
    if not token:
        return None
    try:
        padded = token + "=" * (-len(token) % 4)
        destination = base64.urlsafe_b64decode(padded).decode("utf-8")
    except (UnicodeDecodeError, ValueError):
        return None
    parsed = urlparse(destination)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    return destination


def resolve_tracking_url(url: str, timeout: int = 5, max_redirects: int = 5) -> str:
    """Resolve a newsletter link and return its canonical destination.

    Every redirect hop is validated before it is requested, preventing an email
    from using a tracking link to make the importer fetch an internal service.
    Some providers reject ``HEAD``; in that case a streamed ``GET`` is used
    solely to obtain the response headers.
    """
    if not is_tracking_url(url):
        return url

    if destination := _embedded_destination(url):
        return canonicalize_url(destination)

    for method in ("HEAD", "GET"):
        current_url = url
        try:
            for _ in range(max_redirects + 1):
                validate_url_target(current_url)
                response = requests.request(method, current_url, allow_redirects=False, timeout=timeout, stream=method == "GET")
                try:
                    if response.is_redirect or response.is_permanent_redirect:
                        location = response.headers.get("Location")
                        if not location:
                            raise ValueError("Redirect response has no Location header")
                        current_url = requests.compat.urljoin(current_url, location)
                        continue

                    if 200 <= response.status_code < 400:
                        return canonicalize_url(current_url)

                    # A number of newsletter services do not implement HEAD.
                    if method == "HEAD":
                        break
                    raise ValueError(f"GET returned HTTP {response.status_code}")
                finally:
                    response.close()
            else:
                raise ValueError(f"Too many redirects (>{max_redirects})")
        except (requests.RequestException, ValueError) as exc:
            logger.warning("Could not resolve tracking URL %s: %s", url, exc)
            return url

    return url


def resolve_tracking_urls_in_text(text: str, timeout: int = 5) -> str:
    """Replace known newsletter redirect URLs in plain text with destinations.

    This is the client-independent counterpart to the HTML importer's link
    normalization.  It also makes browser, Gmail API and future import paths
    behave identically.  Regular URLs are never fetched or changed.
    """
    if not text:
        return text

    def replace(match: re.Match) -> str:
        raw = match.group(0)
        suffix = ""
        while raw and raw[-1] in _TRAILING_URL_PUNCTUATION:
            suffix = raw[-1] + suffix
            raw = raw[:-1]
        if not raw or not is_tracking_url(raw):
            return raw + suffix
        return resolve_tracking_url(raw, timeout=timeout) + suffix

    return _TEXT_URL_RE.sub(replace, text)
