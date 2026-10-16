"""run_check() reports which feed was checked and how many items were new."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")

from library import feed_monitor_service as service  # noqa: E402


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
        item = existing if entry["url"] == "old" else object()
        if item is not existing:
            sess.new.add(item)
        return item

    monkeypatch.setattr(service, "_feed_config", lambda f: {})
    monkeypatch.setattr(service, "fetch_entries", lambda cfg: [{"url": "old"}, {"url": "n1"}, {"url": "n2"}])
    monkeypatch.setattr(service, "apply_skip_filters", lambda entries, cfg: (entries[:2], entries[2:]))
    monkeypatch.setattr(service, "_upsert", fake_upsert)

    result = service.run_check(7, session=session)

    assert result == {
        "checked": 1, "items": 3, "new_items": 2, "errors": [],
        "feeds": [{"feed_source_id": 7, "feed_name": "Zaufana Trzecia Strona", "items": 3, "new_items": 2}],
    }


def test_run_check_failed_feed_is_not_listed_in_feeds(monkeypatch):
    feed = SimpleNamespace(id=1, name="Broken", type="rss", url="u", last_error=None)
    monkeypatch.setattr(service, "_feed_config", lambda f: {})
    monkeypatch.setattr(service, "fetch_entries", MagicMock(side_effect=RuntimeError("boom")))

    result = service.run_check(session=_session([feed]))

    assert result["feeds"] == [] and result["checked"] == 0
    assert result["errors"][0]["feed_name"] == "Broken"
