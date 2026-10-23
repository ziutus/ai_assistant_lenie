"""Send a feed item to the tool radar (``/feed-review`` -> "Do radaru").

The radar and the feed review share one purpose - decide whether something is worth
attention now, worth remembering, or worth ignoring. This turns a feed candidate into a
``watchlist`` radar entry (or a new piece of provenance for one already there), keeps the
feed item out of the "new" queue (``skipped`` with review reason ``sent_to_radar``) and lets
``tool_relations_service`` propose its links to the tools already on the radar.
"""

import re

from sqlalchemy import func, or_, select

from library import tool_relations_service
from library.db.models import FeedItem, FeedSource, Tool, ToolRecommendation, ToolRecommendationEvidence
from library.feed_monitor_service import transition_item

REASON = "sent_to_radar"
NAME_MAX_LENGTH = 255
_TITLE_SPLIT = re.compile(r"\s+[-–—]\s+|\s*:\s+|\s*\|\s*")


def suggest_name(title: str) -> str:
    """"Floci - testuj aplikacje chmurowe lokalnie" -> "Floci": the part before the first dash/colon."""
    head = _TITLE_SPLIT.split((title or "").strip(), maxsplit=1)[0].strip()
    return (head or (title or "").strip())[:NAME_MAX_LENGTH]


def _existing(session, name: str, homepage_url: str | None):
    """The radar entry or catalog tool that already stands for this name/homepage, if any."""
    def clauses(model):
        found = [func.lower(model.name) == name.lower()]
        if homepage_url:
            found.append(model.homepage_url == homepage_url)
        return or_(*found)

    recommendation = session.execute(select(ToolRecommendation).where(clauses(ToolRecommendation)).limit(1)).scalars().first()
    if recommendation is not None:
        return recommendation, None
    return None, session.execute(select(Tool).where(clauses(Tool)).limit(1)).scalars().first()


def send_to_radar(session, item_id: int, user_id: int | None, name: str | None = None,
                  homepage_url: str | None = None, category: str | None = None) -> dict:
    """Create/extend the radar entry for a feed item and move the item out of the review queue.

    ``homepage_url=""`` means "no homepage" (the feed item's own URL is then only the source).
    Raises ``ValueError`` for an unknown item or an empty name, ``RuntimeError`` when the item's
    state no longer allows the transition.
    """
    item = session.get(FeedItem, item_id)
    if item is None:
        raise ValueError("feed item not found")
    name = (name or suggest_name(item.title)).strip()[:NAME_MAX_LENGTH]
    if not name:
        raise ValueError("name is required")
    if homepage_url is None:
        homepage_url = item.url
    homepage_url = homepage_url.strip() or None
    feed = session.get(FeedSource, item.feed_source_id)
    feed_name = feed.name if feed is not None else None

    recommendation, tool = _existing(session, name, homepage_url)
    created = recommendation is None and tool is None
    if created:
        recommendation = ToolRecommendation(
            name=name, homepage_url=homepage_url, description=item.summary or item.title,
            category=(category or "").strip() or None, status="watchlist", source_url=item.url,
            source_context=f"Feed: {feed_name}" if feed_name else "Feed",
            source_document_id=item.document_id,
        )
        session.add(recommendation)
        session.flush()
    evidence_added = False
    if recommendation is not None:
        already = session.execute(select(ToolRecommendationEvidence.id).where(
            ToolRecommendationEvidence.tool_recommendation_id == recommendation.id,
            ToolRecommendationEvidence.catalog_url == item.url,
        ).limit(1)).first()
        if already is None:
            session.add(ToolRecommendationEvidence(
                tool_recommendation_id=recommendation.id, relation_type="mentioned_in", catalog_url=item.url,
                catalog_label=feed_name or item.url, context=item.title, recommender_document_id=item.document_id,
            ))
            evidence_added = True
        proposed = tool_relations_service.detect_relations(session, recommendation)["created"] if created else []
    else:
        proposed = []
    try:
        transition_item(session, item_id, "skipped", user_id, REASON)  # commits radar entry and transition together
    except Exception:
        session.rollback()
        raise
    return {
        "created": created,
        "recommendation": None if recommendation is None else {"id": recommendation.id, "name": recommendation.name},
        "existing_tool": None if tool is None else {"id": tool.id, "name": tool.name},
        "evidence_added": evidence_added,
        "proposed_relations": proposed,
    }
