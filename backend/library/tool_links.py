"""Shared handling of the ``links`` lists of radar entries and catalog tools (``[{url, label}]``)."""

from flask import abort

from library import tool_note_parser


def clean_links(raw) -> list[dict]:
    """Validate ``links``: a list of ``{url, label?}`` (or bare URL strings) with http(s) URLs, duplicates dropped."""
    if not isinstance(raw, list) or len(raw) > tool_note_parser.MAX_LINKS:
        abort(400, f"links must be a list of at most {tool_note_parser.MAX_LINKS} items")
    result: list[dict] = []
    seen: set[str] = set()
    for item in raw:
        if isinstance(item, str):
            item = {"url": item}
        if not isinstance(item, dict):
            abort(400, "every link must be {url, label}")
        url = str(item.get("url") or "").strip()
        label = item.get("label")
        if not url.lower().startswith(("http://", "https://")):
            abort(400, f"link url must start with http:// or https://: {url or '(empty)'}")
        if label is not None and not isinstance(label, str):
            abort(400, "link label must be a string")
        if url not in seen:
            seen.add(url)
            result.append({"url": url, "label": (label or "").strip()[:100]})
    return result


def merge_links(existing, extra) -> list[dict]:
    """``existing`` plus the ``extra`` links whose URL is new, capped at ``MAX_LINKS`` (no validation, no abort)."""
    merged: list[dict] = []
    seen: set[str] = set()
    for item in [*(existing or []), *(extra or [])]:
        url = str((item or {}).get("url") or "").strip()
        if url and url not in seen and len(merged) < tool_note_parser.MAX_LINKS:
            seen.add(url)
            merged.append({"url": url, "label": str(item.get("label") or "").strip()[:100]})
    return merged
