"""Deterministic article metadata extraction for supported news portals."""

import json
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup


def _is_wp_url(url: str) -> bool:
    """Grupa Wirtualna Polska portals sharing the same CMS byline widget."""
    host = (urlparse(url).hostname or "").lower()
    return (
        host == "wp.pl"
        or host.endswith(".wp.pl")
        or host == "o2.pl"
        or host.endswith(".o2.pl")
        or host == "money.pl"
        or host.endswith(".money.pl")
    )


def _is_onet_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host == "onet.pl" or host.endswith(".onet.pl")


# money.pl's "cauthor" value sometimes bakes in the "oprac." (opracowanie /
# compiled by) label that is otherwise rendered as a separate <span> next to
# the byline link, e.g. "oprac. Przemysław Ciszak" instead of just the name.
_AUTHOR_LABEL_PREFIX_RE = re.compile(r"^\s*oprac\.?\s*:?\s*", re.IGNORECASE)


def _strip_author_label_prefix(name: str) -> str:
    return _AUTHOR_LABEL_PREFIX_RE.sub("", name).strip()


def _as_types(value) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, list):
        return {item for item in value if isinstance(item, str)}
    return set()


def _author_names(value) -> list[str]:
    values = value if isinstance(value, list) else [value]
    names: list[str] = []
    for item in values:
        name = item.get("name") if isinstance(item, dict) else item if isinstance(item, str) else None
        if name and name.strip() and name.strip().casefold() not in {n.casefold() for n in names}:
            names.append(name.strip())
    return names


def _extract_onet_authors(html: str) -> list[str]:
    """Read the byline from the Article object, never every Person in @graph."""
    soup = BeautifulSoup(html, "html.parser")
    article_types = {"Article", "NewsArticle", "ReportageNewsArticle", "AnalysisNewsArticle"}
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            payload = json.loads(script.string or script.get_text())
        except (json.JSONDecodeError, TypeError):
            continue
        roots = payload if isinstance(payload, list) else [payload]
        for root in roots:
            if not isinstance(root, dict):
                continue
            objects = root.get("@graph", [root])
            if not isinstance(objects, list):
                objects = [objects]
            for obj in objects:
                if isinstance(obj, dict) and _as_types(obj.get("@type")) & article_types:
                    names = _author_names(obj.get("author"))
                    if names:
                        return names

    # Portal-specific fallback: only the compact byline immediately associated
    # with the story. Profile cards later on the page repeat the same people.
    names: list[str] = []
    for link in soup.select('a[href*="/autorzy/"]'):
        if link.find_parent(class_=lambda c: c and "author-xl" in " ".join(c if isinstance(c, list) else [c])):
            continue
        name = link.get_text(" ", strip=True)
        if name and name.casefold() not in {n.casefold() for n in names}:
            names.append(name)
        if len(names) >= 10:
            break
    return names


def extract_article_authors(html: str | None, url: str = "") -> list[str]:
    """Extract all deterministic portal byline authors from raw HTML."""
    if not html:
        return []
    if _is_onet_url(url):
        return _extract_onet_authors(html)
    author = extract_article_author(html, url)
    return [author] if author else []


def extract_article_author(html: str | None, url: str = "") -> str | None:
    """Extract a content author's name from raw HTML.

    WP's standard ``<meta name="author">`` identifies the publisher (usually
    Grupa Wirtualna Polska), not the article byline, so it is intentionally
    ignored.  ``cauthor`` and the visible WP byline are portal-specific and
    refer to the actual content author.
    """
    if not html or not _is_wp_url(url):
        return None

    # WP analytics payload. Parsing the quoted JSON value also handles escaped
    # Unicode without maintaining a second HTML/JS unescape implementation.
    match = re.search(r'"cauthor"\s*:\s*("(?:\\.|[^"\\])*")', html)
    if match:
        try:
            author = json.loads(match.group(1)).strip()
        except (json.JSONDecodeError, AttributeError):
            author = ""
        if author:
            return _strip_author_label_prefix(author)

    soup = BeautifulSoup(html, "html.parser")
    byline = soup.select_one("#wp-article-author-info .wp-article-author-link, .wp-article-author-link")
    if byline:
        author = byline.get_text(" ", strip=True)
        if author:
            return _strip_author_label_prefix(author)

    return None
