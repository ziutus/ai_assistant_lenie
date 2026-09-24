"""Small, deterministic importer for Markdown tables in curated GitHub lists."""

from __future__ import annotations

import re
from urllib.parse import quote, urlparse

import requests

# Bounded quantifiers keep matching linear on adversarial input (CodeQL py/polynomial-redos).
_HEADING = re.compile(r"^#{2,6}[ \t]+(\S.{0,500})$")
_LINK = re.compile(r"\[([^\]\[]{1,300})\]\((https?://[^)\s]{1,2000})\)")
_ALLOWED_HOSTS = {"github.com", "www.github.com", "raw.githubusercontent.com"}
_RAW_HOST = "raw.githubusercontent.com"


def github_raw_url(url: str) -> str:
    """Convert a public GitHub repository/file URL into its raw README URL."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc not in _ALLOWED_HOSTS:
        raise ValueError("source_url must be a public GitHub URL")
    parts = [part for part in parsed.path.split("/") if part]
    if parsed.netloc == _RAW_HOST:
        # Rebuild from validated parts instead of echoing the caller's string.
        return f"https://{_RAW_HOST}/{'/'.join(quote(part, safe='') for part in parts)}"
    if len(parts) < 2:
        raise ValueError("source_url must identify a GitHub repository or Markdown file")
    owner, repository = parts[:2]
    if len(parts) >= 5 and parts[2] == "blob":
        return f"https://raw.githubusercontent.com/{owner}/{repository}/{parts[3]}/{'/'.join(parts[4:])}"
    return f"https://raw.githubusercontent.com/{owner}/{repository}/HEAD/README.md"


def fetch_markdown(source_url: str) -> str:
    # No redirects: the host allowlist is enforced on the URL we build, not on a redirect target.
    response = requests.get(github_raw_url(source_url), timeout=20, allow_redirects=False)
    response.raise_for_status()
    return response.text


def parse_markdown_recommendations(markdown: str) -> list[dict[str, str | None]]:
    """Return entries from Markdown table rows, carrying the nearest heading."""
    category: str | None = None
    items: list[dict[str, str | None]] = []
    seen: set[tuple[str, str]] = set()
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        heading = _HEADING.match(line)
        if heading:
            category = heading.group(1).strip()
            continue
        if not line.startswith("|") or "---" in line:
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if not cells:
            continue
        link = _LINK.search(cells[0])
        if link is None:
            continue
        name, homepage_url = link.groups()
        key = (name.casefold(), homepage_url.rstrip("/"))
        if key in seen:
            continue
        seen.add(key)
        description = cells[-1] if len(cells) > 1 else None
        items.append({"name": name.strip(), "homepage_url": homepage_url, "description": description or None, "category": category})
    return items
