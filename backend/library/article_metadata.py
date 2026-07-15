"""Deterministic article metadata extraction for supported news portals."""

import json
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup


def _is_wp_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host == "wp.pl" or host.endswith(".wp.pl") or host == "o2.pl" or host.endswith(".o2.pl")


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
            return author

    soup = BeautifulSoup(html, "html.parser")
    byline = soup.select_one("#wp-article-author-info .wp-article-author-link, .wp-article-author-link")
    if byline:
        author = byline.get_text(" ", strip=True)
        if author:
            return author

    return None
