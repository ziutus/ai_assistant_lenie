"""run_check() reports which feed was checked and how many items were new."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")

from library import feed_monitor_service as service  # noqa: E402


class _Item:  # hashable (SimpleNamespace is not), as the real FeedItem is held in session.new
    def __init__(self, id, title, url, status):
        self.id, self.title, self.url, self.status = id, title, url, status


def _session(feeds):
    session = MagicMock()
    session.scalars.return_value.all.return_value = feeds
    session.new = set()
    return session


def test_run_check_names_feed_and_counts_new_items(monkeypatch):
    feed = SimpleNamespace(id=7, name="Zaufana Trzecia Strona", type="rss", url="u", last_error=None)
    session = _session([feed])
    existing = object()

    def fake_upsert(sess, f, entry, status="new"):
        if entry["url"] == "old":
            return existing
        item = _Item(100 + len(sess.new), f"t-{entry['url']}", entry["url"], status)
        sess.new.add(item)
        return item

    monkeypatch.setattr(service, "_feed_config", lambda f: {})
    monkeypatch.setattr(service, "fetch_entries", lambda cfg: [{"url": "old"}, {"url": "n1"}, {"url": "n2"}])
    monkeypatch.setattr(service, "apply_skip_filters", lambda entries, cfg: (entries[:2], entries[2:]))
    monkeypatch.setattr(service, "_upsert", fake_upsert)

    result = service.run_check(7, session=session)

    # n2 is an ignored entry: counted in new_items, but not listed for the reader.
    assert result == {
        "checked": 1, "items": 3, "new_items": 2, "errors": [],
        "feeds": [{
            "feed_source_id": 7, "feed_name": "Zaufana Trzecia Strona", "items": 3, "new_items": 2,
            "new_entries": [{"feed_item_id": 100, "title": "t-n1", "url": "n1", "status": "new"}],
            "new_entries_truncated": 0,
        }],
    }


def test_run_check_caps_listed_new_entries(monkeypatch):
    feed = SimpleNamespace(id=7, name="Big", type="rss", url="u", last_error=None)
    session = _session([feed])
    entries = [{"url": f"n{i}"} for i in range(service.NEW_ENTRIES_LISTED + 3)]

    def fake_upsert(sess, f, entry, status="new"):
        item = _Item(len(sess.new), entry["url"], entry["url"], status)
        sess.new.add(item)
        return item

    monkeypatch.setattr(service, "_feed_config", lambda f: {})
    monkeypatch.setattr(service, "fetch_entries", lambda cfg: entries)
    monkeypatch.setattr(service, "apply_skip_filters", lambda e, cfg: (e, []))
    monkeypatch.setattr(service, "_upsert", fake_upsert)

    feed_result = service.run_check(7, session=session)["feeds"][0]

    assert feed_result["new_items"] == len(entries)
    assert len(feed_result["new_entries"]) == service.NEW_ENTRIES_LISTED
    assert feed_result["new_entries_truncated"] == 3


def test_run_check_feed_without_new_items_has_no_entry_list(monkeypatch):
    feed = SimpleNamespace(id=7, name="Quiet", type="rss", url="u", last_error=None)
    monkeypatch.setattr(service, "_feed_config", lambda f: {})
    monkeypatch.setattr(service, "fetch_entries", lambda cfg: [{"url": "old"}])
    monkeypatch.setattr(service, "apply_skip_filters", lambda e, cfg: (e, []))
    monkeypatch.setattr(service, "_upsert", lambda *a, **k: object())

    feed_result = service.run_check(7, session=_session([feed]))["feeds"][0]

    assert "new_entries" not in feed_result


def test_run_check_failed_feed_is_not_listed_in_feeds(monkeypatch):
    feed = SimpleNamespace(id=1, name="Broken", type="rss", url="u", last_error=None)
    monkeypatch.setattr(service, "_feed_config", lambda f: {})
    monkeypatch.setattr(service, "fetch_entries", MagicMock(side_effect=RuntimeError("boom")))

    result = service.run_check(session=_session([feed]))

    assert result["feeds"] == [] and result["checked"] == 0
    assert result["errors"][0]["feed_name"] == "Broken"
