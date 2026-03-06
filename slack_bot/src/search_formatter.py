"""Shared formatter for search results from /website_similar endpoint.

Converts API response to Slack-friendly text format.
"""

from __future__ import annotations

import os


def get_search_results_limit() -> int:
    """Return the max number of search results to display."""
    try:
        return int(os.environ.get("SEARCH_RESULTS_LIMIT", "5"))
    except (ValueError, TypeError):
        return 5


def format_search_results(query: str, results: list[dict]) -> str:
    """Format search results as Slack message text.

    Args:
        query: The original search query.
        results: List of dicts from api_client.search_similar().

    Returns:
        Formatted Slack message string.
    """
    if not results:
        return f"No similar documents found for '{query}'."

    limit = get_search_results_limit()
    limited = results[:limit]

    lines = [f"Found {len(limited)} result{'s' if len(limited) != 1 else ''} for \"{query}\":\n"]

    for i, doc in enumerate(limited, 1):
        title = doc.get("title") or doc.get("url", "Untitled")
        doc_type = doc.get("document_type", "unknown")
        similarity = doc.get("similarity", 0.0)
        url = doc.get("url", "")

        pct = int(similarity * 100)
        lines.append(f"{i}. *{title}* ({doc_type}, {pct}%)")
        if url:
            lines.append(f"   {url}")

    return "\n".join(lines)
