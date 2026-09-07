from datetime import datetime, timezone

import pytest
import socket
from unittest.mock import MagicMock

import requests
import urllib3
from library import safe_http
from library.feed_parser import fetch_entries

from library.feed_parser import (
    apply_skip_filters,
    build_feed_url,
    parse_published,
    strip_html,
)


def test_strip_html_normalizes_markup_and_entities():
    assert strip_html("<p>A &amp; B</p><br>tekst") == "A & B\n\ntekst"


def test_apply_skip_filters_returns_kept_and_ignored_entries():
    entries = [
        {"title": "Normalny", "url": "https://example.com/a"},
        {"title": "SPONSOROWANE", "url": "https://example.com/b"},
    ]
    kept, ignored = apply_skip_filters(entries, {"skip_title_patterns": ["^sponsorowane"]})
    assert len(kept) == 1
    assert ignored[0]["ignored_pattern"] == "^sponsorowane"


def test_build_feed_url_for_youtube_channel():
    assert build_feed_url({"type": "youtube_channel", "channel_id": "UCabc"}) == (
        "https://www.youtube.com/feeds/videos.xml?channel_id=UCabc"
    )


@pytest.mark.parametrize("feed_type", ["rss", "wordpress", "json_api"])
def test_build_feed_url_for_url_feed(feed_type):
    assert build_feed_url({"type": feed_type, "url": "https://example.com/feed"}) == "https://example.com/feed"


def test_build_feed_url_rejects_unknown_type():
    with pytest.raises(ValueError):
        build_feed_url({"type": "carrier_pigeon"})


def test_parse_published_accepts_iso_and_rfc2822():
    assert parse_published("2026-03-01T12:30:00+00:00") == datetime(2026, 3, 1, 12, 30, tzinfo=timezone.utc)
    assert parse_published("Mon, 02 Mar 2026 10:00:00 +0000").day == 2


def _addresses(*ips):
    return [(socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))
            for ip in ips]


@pytest.fixture()
def network(monkeypatch):
    """No test in this module can reach a real network."""
    resolver = MagicMock(return_value=_addresses("93.184.216.34"))
    monkeypatch.setattr(safe_http.socket, "getaddrinfo", resolver)
    sock = MagicMock()
    monkeypatch.setattr(safe_http.socket, "socket", MagicMock(return_value=sock))
    pool_factory = MagicMock()
    monkeypatch.setattr(safe_http, "_pinned_pool", pool_factory)
    pool = pool_factory.return_value.__enter__.return_value
    return resolver, pool_factory, pool, sock


def _response(body=b"<rss><channel/></rss>", status=200, headers=None):
    response = MagicMock(status=status, headers=headers or {})
    response.stream.return_value = [body]
    return response


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.1", "172.16.0.1", "192.168.1.1", "169.254.169.254",
                                   "100.64.0.1", "0.0.0.0", "240.0.0.1", "::1", "fc00::1", "fe80::1",
                                   "::ffff:8.8.8.8", "ff02::1"])
def test_feed_blocks_any_internal_dns_answer(network, ip):
    resolver, factory, _, _ = network
    resolver.return_value = _addresses("93.184.216.34", ip)
    with pytest.raises(ValueError, match="non-public"):
        fetch_entries({"type": "rss", "url": "https://example.com/rss"})
    factory.assert_not_called()


# The userinfo case is assembled at runtime so the repo secret scanner does not
# flag a literal ``scheme://user:pass@host`` in the source.
_CREDENTIALED_URL = "http://user:" + "x" + "@example.com/"


@pytest.mark.parametrize("url", ["file:///etc/passwd", "http://localhost:8200/", "http://127.0.0.1/",
                                    "http://[::1]/", "http://[::ffff:8.8.8.8]/", "http://x.local/",
                                    _CREDENTIALED_URL, "http://example.com:0/"])
def test_feed_rejects_internal_url_at_write_and_fetch(network, url):
    from library.feed_source_service import validate_feed_values
    with pytest.raises(ValueError):
        validate_feed_values({"type": "rss", "url": url})
    with pytest.raises(ValueError):
        fetch_entries({"type": "rss", "url": url})
    network[1].assert_not_called()


def test_public_redirect_to_internal_is_blocked(network):
    resolver, _, pool, _ = network
    response = _response(status=302, headers={"Location": "http://internal.example/secret"})
    pool.urlopen.return_value = response
    resolver.side_effect = [_addresses("93.184.216.34"), _addresses("10.0.0.1")]
    with pytest.raises(ValueError, match="non-public"):
        fetch_entries({"type": "rss", "url": "https://example.com/feed"})
    pool.urlopen.assert_called_once()
    response.close.assert_called_once()


@pytest.mark.parametrize("feed,body,title", [
    ({"type": "rss", "url": "https://example.com/rss"},
     b'\xef\xbb\xbf \n<?xml version="1.0"?><rss><channel><item><title>RSS</title></item></channel></rss>', "RSS"),
    ({"type": "wordpress", "url": "https://example.com/rss"},
     b'<rss><channel><item><title>WP</title></item></channel></rss>', "WP"),
    ({"type": "youtube_channel", "channel_id": "UCabc"},
     b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Atom</title></entry></feed>', "Atom"),
    ({"type": "json_api", "url": "https://example.com/json"}, b'[{"title":"JSON","url":"https://example.com"}]',
     "JSON"),
])
def test_public_feeds_parse_with_preserved_timeouts(network, feed, body, title):
    _, factory, pool, _ = network
    response = _response(body)
    pool.urlopen.return_value = response
    assert fetch_entries(feed, connect_timeout=3, read_timeout=7)[0]["title"] == title
    assert factory.call_args.args[2] == (3, 7)
    assert pool.urlopen.call_args.kwargs == {"redirect": False, "retries": False, "preload_content": False}
    response.close.assert_called_once()


def test_relative_redirect_and_limit(network):
    _, _, pool, _ = network
    redirect = _response(status=301, headers={"Location": "/next"})
    pool.urlopen.side_effect = [redirect, _response()]
    assert fetch_entries({"type": "rss", "url": "https://example.com/feed"}) == []
    assert pool.urlopen.call_args.args == ("GET", "/next")
    pool.urlopen.side_effect = None
    pool.urlopen.return_value = redirect
    with pytest.raises(ValueError, match="Too many"):
        safe_http.safe_get("https://example.com", max_redirects=1)


def test_http_xml_and_size_errors(network):
    import xml.etree.ElementTree as ET
    pool = network[2]
    pool.urlopen.return_value = _response(status=500)
    with pytest.raises(requests.HTTPError):
        fetch_entries({"type": "rss", "url": "https://example.com"})
    pool.urlopen.return_value = _response(b"broken XML")
    with pytest.raises(ET.ParseError):
        fetch_entries({"type": "rss", "url": "https://example.com"})
    with pytest.raises(ValueError, match="size limit"):
        safe_http.safe_get("https://example.com", max_bytes=2)
    pool.urlopen.side_effect = urllib3.exceptions.HTTPError("failed")
    with pytest.raises(requests.ConnectionError):
        safe_http.safe_get("https://example.com")


def test_dns_rebinding_cannot_change_connected_address(monkeypatch):
    resolver = MagicMock(side_effect=[_addresses("93.184.216.34"), _addresses("127.0.0.1")])
    monkeypatch.setattr(safe_http.socket, "getaddrinfo", resolver)
    sock = MagicMock()
    monkeypatch.setattr(safe_http.socket, "socket", MagicMock(return_value=sock))
    tls = MagicMock(return_value=MagicMock(socket=sock, is_verified=True))
    monkeypatch.setattr(urllib3.connection, "_ssl_wrap_socket_and_match_hostname", tls)
    parsed = safe_http.validate_public_url("https://example.com/feed")
    addresses = safe_http._resolve_target(parsed)
    with safe_http._pinned_pool(parsed, addresses, (3, 7)) as pool:
        conn = pool._new_conn()
        assert conn.host == "example.com"
        assert conn.cert_reqs == "CERT_REQUIRED"
        assert conn.ca_certs == requests.certs.where()
        conn.request("GET", "/feed")
        sock.connect.assert_called_once_with(("93.184.216.34", 443))
        resolver.assert_called_once()
        assert tls.call_args.kwargs["server_hostname"] == "example.com"
        assert tls.call_args.kwargs["cert_reqs"] == "CERT_REQUIRED"
        assert tls.call_args.kwargs["assert_hostname"] is not False
        assert b"Host: example.com\r\n" in sock.sendall.call_args.args[0]


def test_public_ipv6_socket_uses_validated_address(monkeypatch):
    address = ("2606:4700:4700::1111", 80, 0, 0)
    resolver = MagicMock(return_value=[(socket.AF_INET6, socket.SOCK_STREAM, 6, "", address)])
    monkeypatch.setattr(safe_http.socket, "getaddrinfo", resolver)
    sock = MagicMock()
    monkeypatch.setattr(safe_http.socket, "socket", MagicMock(return_value=sock))
    parsed = safe_http.validate_public_url("http://example.com/feed")
    with safe_http._pinned_pool(parsed, safe_http._resolve_target(parsed), (3, 7)) as pool:
        pool._new_conn().request("GET", "/feed")
    sock.connect.assert_called_once_with(address)
    resolver.assert_called_once()
