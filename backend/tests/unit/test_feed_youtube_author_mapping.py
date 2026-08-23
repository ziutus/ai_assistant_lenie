"""Explicit YouTube-channel author mappings on feed imports."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("sqlalchemy")

from library.db.models import FeedSource
from library.feed_source_service import feed_to_dict, validate_feed_values
from library.feed_monitor_service import import_feed_item


def test_feed_source_exposes_explicit_youtube_author_name():
    mapper = FeedSource.__mapper__
    assert "author_name" in mapper.columns

    feed = SimpleNamespace(
        id=1, name="Kanał", type="youtube_channel", url=None, channel_id="UC123",
        author_name="Good Times Bad Times", language="pl", collection_id=None, tags=[],
        default_topic_group_ids=[], auto_import=False, disabled=False, auto_import_after=None,
        discovery_source_id=None, default_state="URL_ADDED", field_mapping={},
        skip_url_patterns=[], skip_title_patterns=[], last_checked_at=None,
        last_successful_import_at=None, last_error_at=None, last_error=None,
    )
    assert feed_to_dict(feed)["author_name"] == "Good Times Bad Times"


def test_author_name_is_optional_and_youtube_only():
    values = validate_feed_values({
        "type": "youtube_channel", "channel_id": "UC123", "url": None,
        "author_name": "  Good Times Bad Times  ",
    })
    assert values["author_name"] == "Good Times Bad Times"

    with pytest.raises(ValueError, match="youtube_channel"):
        validate_feed_values({
            "type": "rss", "url": "https://example.com/feed", "channel_id": None,
            "author_name": "Nie dla RSS",
        })


def test_new_youtube_import_creates_structured_author_from_feed_mapping():
    item = SimpleNamespace(
        id=17, feed_source_id=9, canonical_url="https://www.youtube.com/watch?v=abc",
        status="new", document_id=None, saved_at=None, saved_by_user_id=None,
        review_reason=None, ignored_pattern=None, group_memberships=[], last_error=None,
        updated_at=None, title="Film", summary=None, published_at=None,
    )
    feed = SimpleNamespace(
        id=9, type="youtube_channel", author_name="Good Times Bad Times", default_state="URL_ADDED",
        language="pl", tags=[], name="GTBT feed", collection_id=None,
    )
    document = SimpleNamespace(id=123, byline="Good Times Bad Times")
    session = MagicMock()
    session.get.side_effect = lambda model, identifier: item if identifier == 17 else feed

    with (
        patch("library.feed_monitor_service.Document.get_by_url", return_value=None),
        patch("library.feed_monitor_service.DocumentService") as document_service,
        patch("library.feed_monitor_service.copy_feed_groups_to_document"),
        patch("library.feed_monitor_service.record_review_decision"),
        patch("library.author_service.set_document_authors") as set_authors,
    ):
        document_service.return_value.import_document.return_value = (document, "added")
        _item, imported = import_feed_item(17, session=session)

    assert imported is document
    assert document_service.return_value.import_document.call_args.kwargs["byline"] == "Good Times Bad Times"
    set_authors.assert_called_once_with(session, document, ["Good Times Bad Times"], method="manual")


def test_existing_document_keeps_its_existing_authors():
    item = SimpleNamespace(
        id=17, feed_source_id=9, canonical_url="https://www.youtube.com/watch?v=abc",
        status="new", document_id=None, saved_at=None, saved_by_user_id=None,
        review_reason=None, ignored_pattern=None, group_memberships=[], last_error=None,
        updated_at=None, title="Film", summary=None, published_at=None,
    )
    document = SimpleNamespace(id=123)
    session = MagicMock()
    session.get.return_value = item

    with (
        patch("library.feed_monitor_service.Document.get_by_url", return_value=document),
        patch("library.feed_monitor_service.copy_feed_groups_to_document"),
        patch("library.feed_monitor_service.record_review_decision"),
        patch("library.author_service.set_document_authors") as set_authors,
    ):
        _item, imported = import_feed_item(17, session=session)

    assert imported is document
    set_authors.assert_not_called()
