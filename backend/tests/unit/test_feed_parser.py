from datetime import datetime, timezone

import pytest

from library.feed_parser import (
    apply_skip_filters,
    build_feed_url,
    parse_published,
    strip_html,
)


def test_strip_html_normalizes_markup_and_entities():
    assert strip_html("<p>A &amp; B</p><br>tekst") == "A & B\n\ntekst"


def test_apply_skip_filters_returns_kept_and_ignored_entries():
    entries = [
        {"title": "Normalny", "url": "https://example.com/a"},
        {"title": "SPONSOROWANE", "url": "https://example.com/b"},
    ]
    kept, ignored = apply_skip_filters(entries, {"skip_title_patterns": ["^sponsorowane"]})
    assert len(kept) == 1
    assert ignored[0]["ignored_pattern"] == "^sponsorowane"


def test_build_feed_url_for_youtube_channel():
    assert build_feed_url({"type": "youtube_channel", "channel_id": "UCabc"}) == (
        "https://www.youtube.com/feeds/videos.xml?channel_id=UCabc"
    )


@pytest.mark.parametrize("feed_type", ["rss", "wordpress", "json_api"])
def test_build_feed_url_for_url_feed(feed_type):
    assert build_feed_url({"type": feed_type, "url": "https://example.com/feed"}) == "https://example.com/feed"


def test_build_feed_url_rejects_unknown_type():
    with pytest.raises(ValueError):
        build_feed_url({"type": "carrier_pigeon"})


def test_parse_published_accepts_iso_and_rfc2822():
    assert parse_published("2026-03-01T12:30:00+00:00") == datetime(2026, 3, 1, 12, 30, tzinfo=timezone.utc)
    assert parse_published("Mon, 02 Mar 2026 10:00:00 +0000").day == 2
