import pytest

from library.publisher_domain import normalize_publisher_domain, registrable_domain


@pytest.mark.parametrize(("raw", "expected"), [
    (" WWW.Example.COM. ", "example.com"),
    ("example.com", "example.com"),
    ("", None),
    (None, None),
    ("   ", None),
])
def test_normalize_publisher_domain(raw, expected):
    assert normalize_publisher_domain(raw) == expected


@pytest.mark.parametrize(("raw", "expected"), [
    # Multi-section corporate sites merge under the shared organization domain.
    ("https://tech.wp.pl/artykul-123", "wp.pl"),
    ("wiadomosci.wp.pl", "wp.pl"),
    ("wp.pl", "wp.pl"),
    ("wydarzenia.interia.pl", "interia.pl"),
    ("wiadomosci.onet.pl", "onet.pl"),
    ("docs.google.com", "google.com"),
    ("developer.mozilla.org", "mozilla.org"),
    # A shared PUBLIC suffix must NOT merge unrelated entities.
    ("knf.gov.pl", "knf.gov.pl"),
    ("nik.gov.pl", "nik.gov.pl"),
    ("businessinsider.com.pl", "businessinsider.com.pl"),
    ("botland.com.pl", "botland.com.pl"),
    ("independent.co.uk", "independent.co.uk"),
    ("cable.co.uk", "cable.co.uk"),
    # Multi-tenant hosting platforms in the Public Suffix List stay per-tenant.
    ("foo.github.io", "foo.github.io"),
    ("bar.github.io", "bar.github.io"),
    ("chronotrains-eu.vercel.app", "chronotrains-eu.vercel.app"),
    ("day.js.org", "day.js.org"),
    # Platforms confirmed NOT in the standard PSL get the same per-tenant treatment.
    ("andrewchen.substack.com", "andrewchen.substack.com"),
    ("kbrzozova.medium.com", "kbrzozova.medium.com"),
    ("medium.com", "medium.com"),
    ("link.medium.com", "link.medium.com"),
    # Casing/scheme/path/www noise is stripped before extraction.
    ("HTTPS://WWW.Onet.PL/some/path?x=1", "onet.pl"),
    # No public suffix to resolve against: fall back to the hostname itself.
    ("localhost", "localhost"),
    ("192.168.1.1", "192.168.1.1"),
    # A non-http(s) scheme (e.g. email_import.py's "gmail://<message-id>")
    # must not be misparsed as a hostname.
    ("gmail://0192abcd", None),
    ("", None),
    (None, None),
])
def test_registrable_domain(raw, expected):
    assert registrable_domain(raw) == expected
