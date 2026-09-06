"""Unit tests for SSRF protection in library/website/website_download_context.py."""
import socket
from unittest.mock import MagicMock

import pytest

from library import safe_http
from library.website import website_download_context
from library.website.website_download_context import download_raw_html, validate_url_target

# Public IP literals keep validate_url_target off the network (no hostname to resolve).
PUBLIC_IP = "93.184.216.34"


class TestValidateUrlTarget:
    def test_rejects_non_http_scheme(self):
        with pytest.raises(ValueError, match="Unsupported URL scheme"):
            validate_url_target("ftp://example.com/file.txt")

    def test_rejects_file_scheme(self):
        with pytest.raises(ValueError, match="Unsupported URL scheme"):
            validate_url_target("file:///etc/passwd")

    def test_rejects_missing_hostname(self):
        with pytest.raises(ValueError, match="no hostname"):
            validate_url_target("http://")

    def test_rejects_loopback_address(self):
        with pytest.raises(ValueError, match="non-public address"):
            validate_url_target("http://127.0.0.1:5000/admin")

    def test_rejects_private_address(self):
        with pytest.raises(ValueError, match="non-public address"):
            validate_url_target("http://192.168.200.7:5434/")

    def test_rejects_link_local_address(self):
        # AWS/GCP metadata endpoint — classic SSRF target
        with pytest.raises(ValueError, match="non-public address"):
            validate_url_target("http://169.254.169.254/latest/meta-data/")

    def test_rejects_unresolvable_hostname(self):
        with pytest.raises(ValueError, match="Cannot resolve"):
            validate_url_target("http://nonexistent-domain-lenie-test.invalid/")

    def test_accepts_public_address(self):
        validate_url_target("https://1.1.1.1/")


def _addresses(*ips, port=443):
    return [
        (socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))
        for ip in ips
    ]


def _urllib3_response(*, status=200, body=b"<html></html>", headers=None):
    response = MagicMock(status=status, headers=headers or {})
    response.stream.return_value = [body] if body else []
    return response


@pytest.fixture()
def pinned(monkeypatch):
    """Drive safe_get without a real socket: resolver + connection pool are mocked."""
    resolver = MagicMock(return_value=_addresses(PUBLIC_IP))
    monkeypatch.setattr(safe_http.socket, "getaddrinfo", resolver)
    monkeypatch.setattr(safe_http.socket, "socket", MagicMock(return_value=MagicMock()))
    pool_factory = MagicMock()
    monkeypatch.setattr(safe_http, "_pinned_pool", pool_factory)
    pool = pool_factory.return_value.__enter__.return_value
    return resolver, pool_factory, pool


class TestDownloadRawHtml:
    def test_downloads_content(self, pinned):
        _, _, pool = pinned
        pool.urlopen.return_value = _urllib3_response(body=b"<html>ok</html>")
        assert download_raw_html(f"https://{PUBLIC_IP}/page") == b"<html>ok</html>"
        assert pool.urlopen.call_args.args[0] == "GET"
        assert pool.urlopen.call_args.kwargs["redirect"] is False

    def test_returns_none_on_error_status(self, pinned):
        _, _, pool = pinned
        pool.urlopen.return_value = _urllib3_response(status=404, body=b"nope")
        assert download_raw_html(f"https://{PUBLIC_IP}/missing") is None

    def test_rejects_redirect_to_private_address(self, pinned):
        _, _, pool = pinned
        pool.urlopen.return_value = _urllib3_response(status=302, headers={"Location": "http://192.168.1.1/internal"})
        with pytest.raises(ValueError, match="non-public address"):
            download_raw_html(f"https://{PUBLIC_IP}/redirect")

    def test_follows_public_redirect(self, pinned):
        _, _, pool = pinned
        pool.urlopen.side_effect = [
            _urllib3_response(status=301, headers={"Location": f"https://{PUBLIC_IP}/final"}),
            _urllib3_response(body=b"ok"),
        ]
        assert download_raw_html(f"https://{PUBLIC_IP}/start") == b"ok"

    def test_raises_on_redirect_loop(self, pinned):
        _, _, pool = pinned
        pool.urlopen.return_value = _urllib3_response(
            status=302, headers={"Location": f"https://{PUBLIC_IP}/loop"}
        )
        with pytest.raises(ValueError, match="Too many redirects"):
            download_raw_html(f"https://{PUBLIC_IP}/loop")

    def test_rejects_private_url_before_any_request(self):
        with pytest.raises(ValueError, match="non-public address"):
            download_raw_html("http://127.0.0.1:8080/")

    def test_enforces_response_size_cap(self, pinned, monkeypatch):
        _, _, pool = pinned
        monkeypatch.setattr(website_download_context, "MAX_HTML_BYTES", 8)
        pool.urlopen.return_value = _urllib3_response(body=b"x" * 64)
        with pytest.raises(ValueError, match="size limit"):
            download_raw_html(f"https://{PUBLIC_IP}/big")


def test_dns_rebinding_cannot_redirect_the_socket_inward(monkeypatch):
    """Host resolves public at validation, internal at connect time — must still connect public."""
    resolver = MagicMock(side_effect=[_addresses(PUBLIC_IP), _addresses("127.0.0.1")])
    monkeypatch.setattr(safe_http.socket, "getaddrinfo", resolver)
    created = []

    def _socket(*_a, **_k):
        sock = MagicMock()
        created.append(sock)
        return sock

    monkeypatch.setattr(safe_http.socket, "socket", _socket)

    parsed = safe_http.validate_public_url("https://example.com/page")
    with safe_http._pinned_pool(parsed, safe_http._resolve_target(parsed), (3, 7)) as pool:
        pool._new_conn()._new_conn()  # exercise the pinned socket-creation override

    assert created, "a socket should have been created"
    for sock in created:
        sock.connect.assert_called_once_with((PUBLIC_IP, 443))
    resolver.assert_called_once()  # no second DNS lookup at connect time
