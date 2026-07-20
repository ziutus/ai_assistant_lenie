"""Stable URL canonicalization used for document identity and deduplication."""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


_TRACKING_PARAMS = {
    "_ga", "_gl", "dclid", "fbclid", "gclid", "gbraid", "igshid",
    "msclkid", "twclid", "wbraid",
}
_TRACKING_PREFIXES = ("utm_", "mc_", "ss_", "vero_")


def _is_tracking_param(name: str) -> bool:
    lowered = name.lower()
    return lowered in _TRACKING_PARAMS or lowered.startswith(_TRACKING_PREFIXES)


def canonicalize_url(url: str) -> str:
    """Return a conservative canonical identity for an absolute URL.

    The original URL remains the fetch/display address. This value is only a
    comparison key: fragments and known tracking parameters are discarded,
    while all potentially content-selecting query parameters are preserved.
    """
    value = (url or "").strip()
    if not value:
        raise ValueError("URL cannot be empty")

    try:
        parsed = urlsplit(value)
    except ValueError:
        # Keep malformed legacy values migratable and comparable. Callers that
        # fetch URLs remain responsible for rejecting them.
        return value.split("#", 1)[0]

    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower().rstrip(".")
    try:
        hostname = hostname.encode("idna").decode("ascii")
    except UnicodeError:
        pass

    host = f"[{hostname}]" if ":" in hostname else hostname
    try:
        port = parsed.port
    except ValueError:
        port = None
    if port is not None and not ((scheme == "http" and port == 80) or
                                 (scheme == "https" and port == 443)):
        host = f"{host}:{port}"
    if parsed.username:
        credentials = parsed.username
        if parsed.password:
            credentials += f":{parsed.password}"
        host = f"{credentials}@{host}"

    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/") or "/"

    query_items = [
        (key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not _is_tracking_param(key)
    ]

    # Known equivalent YouTube forms share one identity.
    if hostname in {"youtu.be", "www.youtu.be"}:
        video_id = path.strip("/").split("/", 1)[0]
        if video_id:
            host, path, query_items = "www.youtube.com", "/watch", [("v", video_id)]
    elif hostname in {"youtube.com", "www.youtube.com", "m.youtube.com"} and path == "/watch":
        video_ids = [value for key, value in query_items if key == "v"]
        if video_ids:
            host, query_items = "www.youtube.com", [("v", video_ids[0])]

    query = urlencode(sorted(query_items), doseq=True)
    return urlunsplit((scheme, host, path, query, ""))
