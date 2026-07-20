"""Registrable-domain (eTLD+1) computation shared by Publisher creation/resolution.

Public Suffix List-aware via tldextract, not a naive "last two labels" split.
A naive split would incorrectly merge unrelated entities that merely share a
public suffix — Polish government agencies (knf.gov.pl, nik.gov.pl are
different bodies), companies under a shared second-level suffix (com.pl,
co.uk work the same way) — while *failing* to keep apart per-user
subdomains on multi-tenant hosting platforms (foo.github.io, foo.vercel.app,
foo.netlify.app), which register themselves in the PSL specifically so each
tenant's subdomain counts as its own registrable domain.

`_EXTRA_PRIVATE_SUFFIXES` covers platforms confirmed (2026-07-20, by dry-
running this corpus's actual publisher_domains through registrable_domain())
to have the same per-tenant-subdomain shape but that are *not* in the
standard PSL: without it, every Substack newsletter, Medium/Hashnode/
WordPress.com/Tumblr/Bearblog author, or mikr.us (a Polish per-user VPS
host, subdomain-per-customer) would merge into one "publisher". Extend only
when a migration's merge report or new import data actually shows another
such platform over-merging — this is a small, evidence-driven list, not a
generic blog-platform registry.
"""

from urllib.parse import urlsplit

import tldextract

_EXTRA_PRIVATE_SUFFIXES = (
    "substack.com", "medium.com", "hashnode.dev", "wordpress.com", "tumblr.com",
    "bearblog.dev", "mikr.us",
)

# cache_dir=None: never touch disk: no dependency on a writable cache
# directory inside the backend/NAS container. suffix_list_urls=(): never
# fetch over HTTP; fallback_to_snapshot (default True) uses the PSL
# snapshot bundled in the tldextract package instead.
_extract = tldextract.TLDExtract(
    cache_dir=None, suffix_list_urls=(), include_psl_private_domains=True,
    extra_suffixes=_EXTRA_PRIVATE_SUFFIXES,
)


def normalize_publisher_domain(value: str | None) -> str | None:
    value = (value or "").strip().casefold().rstrip(".")
    if value.startswith("www."):
        value = value[4:]
    return value or None


def registrable_domain(url_or_hostname: str | None) -> str | None:
    """The registrable domain (eTLD+1) for an http(s) URL or bare hostname, or None.

    Rejects non-http(s) schemes (e.g. email_import.py's synthetic
    "gmail://<message-id>" identifiers) rather than misparsing the
    scheme-specific part as a hostname — an email has no publishing portal
    to begin with, and blindly extracting one here would mint a junk
    Publisher row per message.

    Falls back to the normalized hostname itself when tldextract can't
    resolve a public suffix (localhost, bare IPs, a hostname that *is*
    exactly one of _EXTRA_PRIVATE_SUFFIXES with no subdomain).
    """
    value = (url_or_hostname or "").strip()
    if "//" in value:
        parsed = urlsplit(value)
        if parsed.scheme and parsed.scheme not in ("http", "https"):
            return None
        hostname = parsed.hostname
    else:
        hostname = value
    hostname = normalize_publisher_domain(hostname)
    if not hostname:
        return None
    return _extract(hostname).top_domain_under_public_suffix or hostname
