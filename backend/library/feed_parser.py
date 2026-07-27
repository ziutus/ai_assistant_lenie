"""Pure feed parsing and fetching primitives used by the worker.

This module deliberately has no dependency on ``library.imports`` or local
cache files.  Network callers receive one raw payload per normalized item.
"""

import html
import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime
from typing import Any

import defusedxml.ElementTree as DET
import requests

ATOM_NS = "http://www.w3.org/2005/Atom"
MEDIA_NS = "http://search.yahoo.com/mrss/"
ALLOWED_TYPES = {"rss", "wordpress", "youtube_channel", "json_api"}


def build_feed_url(feed: dict) -> str:
    if feed["type"] == "youtube_channel":
        return f"https://www.youtube.com/feeds/videos.xml?channel_id={feed['channel_id']}"
    if feed["type"] in ALLOWED_TYPES:
        return feed["url"]
    raise ValueError(f"Unknown feed type: {feed['type']}")


def strip_html(value: str) -> str:
    if not value or "<" not in value:
        return value or ""
    value = re.sub(r"<br\s*/?>|</?p\s*>", "\n", value, flags=re.I)
    value = re.sub(r"<[^>]+>", "", value)
    return re.sub(r"\n{3,}", "\n\n", html.unescape(value)).strip()


def _text(parent: ET.Element, path: str) -> str:
    node = parent.find(path)
    return (node.text or "").strip() if node is not None else ""


def parse_atom_entries(root: ET.Element) -> list[dict]:
    result = []
    for entry in root.findall(f"{{{ATOM_NS}}}entry"):
        link = entry.find(f"{{{ATOM_NS}}}link")
        desc = entry.find(f"{{{MEDIA_NS}}}group/{{{MEDIA_NS}}}description")
        result.append(
            {
                "title": _text(entry, f"{{{ATOM_NS}}}title"),
                "url": link.get("href", "") if link is not None else "",
                "published": _text(entry, f"{{{ATOM_NS}}}published"),
                "summary": strip_html(desc.text or "" if desc is not None else ""),
                "raw_payload": {"xml": ET.tostring(entry, encoding="unicode")},
            }
        )
    return result


def parse_rss_entries(root: ET.Element) -> list[dict]:
    channel = root.find("channel")
    if channel is None:
        return []
    result = []
    for item in channel.findall("item"):
        published = _text(item, "pubDate")
        try:
            published = parsedate_to_datetime(published).isoformat() if published else ""
        except (TypeError, ValueError):
            pass
        result.append(
            {
                "title": _text(item, "title"),
                "url": _text(item, "link"),
                "published": published,
                "summary": strip_html(_text(item, "description")),
                "raw_payload": {"xml": ET.tostring(item, encoding="unicode")},
            }
        )
    return result


def parse_json_entries(raw: list[dict], feed: dict) -> list[dict]:
    mapping = feed.get("field_mapping") or {}
    result = []
    for item in raw:
        result.append(
            {
                "title": str(item.get(mapping.get("title", "title"), "")).strip(),
                "url": str(item.get(mapping.get("url", "url"), "")).strip(),
                "published": str(item.get(mapping.get("date", "date"), "")).strip(),
                "summary": str(item.get(mapping.get("summary", "summary"), "")).strip(),
                "raw_payload": item,
            }
        )
    return result


def apply_skip_filters(entries: list[dict], feed: dict) -> tuple[list[dict], list[dict]]:
    urls, titles = feed.get("skip_url_patterns") or [], feed.get("skip_title_patterns") or []
    kept, ignored = [], []
    for entry in entries:
        pattern = next((p for p in urls if entry["url"].startswith(p)), None)
        if pattern is None:
            for candidate in titles:
                try:
                    if re.search(candidate, entry["title"], re.I):
                        pattern = candidate
                        break
                except re.error:
                    continue
        (ignored if pattern is not None else kept).append({**entry, "ignored_pattern": pattern} if pattern else entry)
    return kept, ignored


def fetch_entries(feed: dict, *, connect_timeout: float = 10, read_timeout: float = 60) -> list[dict]:
    response = requests.get(build_feed_url(feed), timeout=(connect_timeout, read_timeout))
    response.raise_for_status()
    if feed["type"] == "json_api":
        payload: Any = response.json()
        if not isinstance(payload, list):
            raise ValueError("JSON feed must contain a list")
        return parse_json_entries(payload, feed)
    # Some otherwise valid RSS endpoints emit a UTF-8 BOM or whitespace
    # before the XML declaration. ElementTree rejects that declaration unless
    # it starts at byte zero, so remove only those harmless leading bytes.
    xml_payload = response.content.lstrip(b"\xef\xbb\xbf \t\r\n")
    root = DET.fromstring(xml_payload)
    return parse_atom_entries(root) if root.tag == f"{{{ATOM_NS}}}feed" else parse_rss_entries(root)


def parse_published(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed
    except ValueError:
        try:
            return parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
