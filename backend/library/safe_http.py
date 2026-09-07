"""Bounded public HTTP requests with DNS pinned at the socket boundary.

Shared by the feed worker and the webpage/tracking-link downloaders: a host is
resolved once, every resulting address must be public, and the socket connects
to that validated address while the original hostname is kept for Host, SNI and
certificate verification. Redirects are followed manually, re-validating each
hop, so a hostname that flips to an internal address after the first lookup
cannot be reached.
"""

import ipaddress
import socket
from urllib.parse import urljoin, urlsplit

import requests
import urllib3
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.exceptions import NewConnectionError

MAX_RESPONSE_BYTES = 5 * 1024 * 1024
REDIRECT_STATUSES = {301, 302, 303, 307, 308}


def _public_address(value: str) -> None:
    ip = ipaddress.ip_address(value)
    if not ip.is_global or ip.is_reserved or ip.is_multicast or getattr(ip, "ipv4_mapped", None) is not None:
        raise ValueError("URL resolves to a non-public address")


def validate_public_url(url: str):
    """Syntax/literal checks done before any socket work; DNS is checked again when fetching."""
    if not isinstance(url, str) or any(ord(char) <= 32 for char in url) or "\\" in url:
        raise ValueError("Invalid URL")
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("URL must use http or https and have a hostname")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URL credentials are not supported")
    if parsed.port == 0:
        raise ValueError("Invalid URL port")
    host = parsed.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")) or "%" in host:
        raise ValueError("Internal hostname is not allowed")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass  # Hostnames (including unusual numeric spellings) are resolved below at fetch time.
    else:
        _public_address(host)
    return parsed


def _resolve_target(parsed):
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        addresses = socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("Cannot resolve hostname") from exc
    if not addresses:
        raise ValueError("Hostname has no addresses")
    for family, _, _, _, address in addresses:
        if family not in (socket.AF_INET, socket.AF_INET6):
            raise ValueError("Unsupported address family")
        _public_address(address[0])
    return addresses


def _pinned_pool(parsed, addresses, timeout):
    # Override only socket creation: urllib3 retains the original hostname for
    # Host, SNI and certificate verification. No second DNS lookup, global DNS
    # monkeypatch, environment proxy, or connection reuse across validated hops.
    base = HTTPSConnection if parsed.scheme == "https" else HTTPConnection

    class PinnedConnection(base):
        def _new_conn(self):
            last_error = None
            for family, socktype, proto, _, address in addresses:
                sock = socket.socket(family, socktype, proto)
                try:
                    sock.settimeout(self.timeout)
                    for option in self.socket_options or []:
                        sock.setsockopt(*option)
                    sock.connect(address)
                    return sock
                except OSError as exc:
                    sock.close()
                    last_error = exc
            raise NewConnectionError(self, "Cannot connect to validated address") from last_error

    kwargs = {"timeout": urllib3.Timeout(connect=timeout[0], read=timeout[1])}
    pool_type = urllib3.HTTPConnectionPool
    if parsed.scheme == "https":
        pool_type = urllib3.HTTPSConnectionPool
        kwargs.update(cert_reqs="CERT_REQUIRED", ca_certs=requests.certs.where())
    pool = pool_type(parsed.hostname, port=parsed.port, **kwargs)
    pool.ConnectionCls = PinnedConnection
    return pool


def safe_get(
    url: str, *, method: str = "GET", timeout=(10, 60), max_redirects=5, max_bytes=MAX_RESPONSE_BYTES
) -> requests.Response:
    """Fetch a public URL, revalidating every redirect and capping decoded bytes.

    Redirects are followed with ``GET`` regardless of ``method`` (matching the
    common browser/``requests`` behaviour for tracking links); ``method`` only
    applies to the first hop, so ``HEAD`` still avoids downloading a body.
    """
    hop_method = method.upper()
    for hop in range(max_redirects + 1):
        parsed = validate_public_url(url)
        addresses = _resolve_target(parsed)
        try:
            with _pinned_pool(parsed, addresses, timeout) as pool:
                target = parsed.path or "/"
                if parsed.query:
                    target += "?" + parsed.query
                response = pool.urlopen(hop_method, target, redirect=False, retries=False, preload_content=False)
                try:
                    if response.status in REDIRECT_STATUSES and response.headers.get("Location"):
                        if hop == max_redirects:
                            raise ValueError("Too many redirects")
                        url = urljoin(url, response.headers["Location"])
                        hop_method = "GET"
                        continue
                    body = bytearray()
                    for chunk in response.stream(64 * 1024, decode_content=True):
                        if len(body) + len(chunk) > max_bytes:
                            raise ValueError("Response exceeds size limit")
                        body.extend(chunk)
                    result = requests.Response()
                    result.status_code = response.status
                    result.headers.update(response.headers)
                    result.url = url
                    result._content = bytes(body)
                    return result
                finally:
                    response.close()
        except urllib3.exceptions.HTTPError as exc:
            raise requests.ConnectionError("HTTP request failed") from exc
    raise ValueError("Too many redirects")
