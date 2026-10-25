import datetime as dt
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("flask")

from flask import Flask, g

from library import app_settings, content_group_service as groups_service, feed_monitor_service, feed_retention as fr, feed_routes

UTC = dt.timezone.utc
NOW = dt.datetime(2027, 1, 15, 4, 0, tzinfo=UTC)


def group(kind="topic", rank=None, months=None, archived=None):
    return SimpleNamespace(kind=kind, priority_rank=rank, retention_months=months, archived_at=archived)


def item(item_id, groups, saved_at, status="saved_for_later", title="t"):
    return SimpleNamespace(id=item_id, title=title, status=status, saved_at=saved_at,
                           group_memberships=[SimpleNamespace(group=value) for value in groups])


MAYBE = group("priority", 100)


@pytest.mark.parametrize("start,months,expected", [
    (dt.datetime(2026, 1, 31, tzinfo=UTC), 1, dt.datetime(2026, 2, 28, tzinfo=UTC)),
    (dt.datetime(2027, 8, 31, tzinfo=UTC), 6, dt.datetime(2028, 2, 29, tzinfo=UTC)),  # leap year
    (dt.datetime(2026, 7, 27, 10, 30, tzinfo=UTC), 6, dt.datetime(2027, 1, 27, 10, 30, tzinfo=UTC)),
    (dt.datetime(2026, 12, 15, tzinfo=UTC), 1, dt.datetime(2027, 1, 15, tzinfo=UTC)),
    (dt.datetime(2026, 3, 10, tzinfo=UTC), 12, dt.datetime(2027, 3, 10, tzinfo=UTC)),
])
def test_add_months_uses_calendar_months(start, months, expected):
    assert fr.add_months(start, months) == expected


def test_only_saved_maybe_later_items_expire_and_the_default_applies():
    saved = dt.datetime(2026, 7, 27, tzinfo=UTC)
    assert fr.expiry(item(1, [MAYBE, group()], saved), 6) == (dt.datetime(2027, 1, 27, tzinfo=UTC), 6)
    assert fr.expiry(item(2, [group()], saved), 6) is None  # no "Może kiedyś" priority
    assert fr.expiry(item(3, [group("priority", 10)], saved), 6) is None  # another priority
    assert fr.expiry(item(4, [MAYBE], saved, status="new"), 6) is None
    assert fr.expiry(item(5, [MAYBE], None), 6) is None
    assert fr.expiry(item(6, [group("priority", 100, archived=NOW)], saved), 6) is None


def test_the_longest_topic_retention_wins_and_archived_topics_do_not_count():
    saved = dt.datetime(2026, 7, 27, tzinfo=UTC)
    topics = [group(months=3), group(months=12), group(months=24, archived=NOW), group()]
    assert fr.retention_months(item(1, [MAYBE, *topics], saved), 6) == 12
    assert fr.retention_months(item(2, [MAYBE, group()], saved), 6) == 6
    assert fr.expiry_fields(item(3, [MAYBE, group(months=12)], saved), 6) == {
        "expires_at": "2027-07-27T00:00:00+00:00", "retention_months": 12}
    assert fr.expiry_fields(item(4, [group()], saved), 6) == {"expires_at": None, "retention_months": None}


def session_with(items, default=None, monkeypatch=None):
    session = MagicMock()
    session.scalars.return_value.all.return_value = items
    monkeypatch.setattr(app_settings, "get_setting", lambda *_: default)
    return session


def test_expire_skips_only_items_past_their_term(monkeypatch):
    old, fresh, long_topic = dt.datetime(2026, 7, 1, tzinfo=UTC), dt.datetime(2026, 12, 1, tzinfo=UTC), dt.datetime(2026, 7, 1, tzinfo=UTC)
    items = [item(1, [MAYBE], old), item(2, [MAYBE], fresh), item(3, [MAYBE, group(months=12)], long_topic), item(4, [group()], old)]
    transition = MagicMock()
    monkeypatch.setattr(feed_monitor_service, "transition_item", transition)
    result = fr.expire_saved_items(session_with(items, monkeypatch=monkeypatch), now=NOW)
    assert (result["due"], result["expired"], result["default_months"]) == (1, 1, 6)
    assert [entry["id"] for entry in result["items"]] == [1]
    transition.assert_called_once()
    assert transition.call_args.args[1:3] == (1, "skipped") and transition.call_args.kwargs == {"review_reason": "expired"}


def test_dry_run_changes_nothing_and_uses_the_saved_default(monkeypatch):
    items = [item(1, [MAYBE], dt.datetime(2026, 9, 1, tzinfo=UTC))]  # 3 months old: due only with a 3-month default
    transition = MagicMock()
    monkeypatch.setattr(feed_monitor_service, "transition_item", transition)
    result = fr.expire_saved_items(session_with(items, default=3, monkeypatch=monkeypatch), now=NOW, dry_run=True)
    assert (result["due"], result["expired"], result["dry_run"], result["default_months"]) == (1, 0, True, 3)
    transition.assert_not_called()


def test_a_concurrent_change_is_reported_and_does_not_stop_the_run(monkeypatch):
    items = [item(1, [MAYBE], dt.datetime(2026, 1, 1, tzinfo=UTC)), item(2, [MAYBE], dt.datetime(2026, 1, 2, tzinfo=UTC))]
    calls = []

    def transition(_session, item_id, *_args, **_kwargs):
        calls.append(item_id)
        if item_id == 1:
            raise RuntimeError("feed item was changed concurrently")

    monkeypatch.setattr(feed_monitor_service, "transition_item", transition)
    session = session_with(items, monkeypatch=monkeypatch)
    result = fr.expire_saved_items(session, now=NOW)
    assert calls == [1, 2] and result["expired"] == 1
    assert result["failed"] == [{"id": 1, "error": "feed item was changed concurrently"}]
    session.rollback.assert_called_once()


def test_expired_is_an_accepted_review_reason():
    assert "expired" in feed_monitor_service.REVIEW_REASONS


@pytest.mark.parametrize("value,kind,ok", [
    (None, "topic", True), (6, "topic", True), (120, "topic", True), (1, "topic", True),
    (0, "topic", False), (121, "topic", False), (True, "topic", False), ("6", "topic", False), (6.5, "topic", False),
    (6, "priority", False), (None, "priority", True),
])
def test_topic_retention_validation(value, kind, ok):
    if ok:
        assert groups_service.validate_retention_months(value, kind) == value
    else:
        with pytest.raises(ValueError):
            groups_service.validate_retention_months(value, kind)


@pytest.fixture
def client(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(feed_routes.bp)

    @app.before_request
    def auth():
        g.auth = SimpleNamespace(kind="user", user_id=1)

    session = MagicMock()
    monkeypatch.setattr(feed_routes, "get_scoped_session", lambda: session)
    return app.test_client(), session


def test_retention_default_routes(client, monkeypatch):
    http, _ = client
    stored = {}
    monkeypatch.setattr(app_settings, "get_setting", lambda _s, key, default=None: stored.get(key, default))
    monkeypatch.setattr(app_settings, "set_setting", lambda _s, key, value: stored.update({key: value}) if value is not None else stored.pop(key, None))
    assert http.get("/feed_items/retention").json == {"default_months": 6, "saved": False, "built_in_months": 6, "min": 1, "max": 120}
    assert http.put("/feed_items/retention", json={"default_months": 9}).json == {"default_months": 9, "saved": True}
    assert http.get("/feed_items/retention").json["default_months"] == 9
    for bad in (0, 121, "6", True, 1.5):
        assert http.put("/feed_items/retention", json={"default_months": bad}).status_code == 400
    assert http.put("/feed_items/retention", json={}).status_code == 400
    assert http.put("/feed_items/retention", json={"default_months": None}).json == {"default_months": 6, "saved": False}


def test_expire_saved_route_passes_dry_run(client, monkeypatch):
    http, _ = client
    run = MagicMock(return_value={"dry_run": True, "due": 2, "expired": 0, "failed": [], "default_months": 6, "items": []})
    monkeypatch.setattr(fr, "expire_saved_items", run)
    assert http.post("/feed_items/expire_saved", json={"dry_run": True}).json["due"] == 2
    assert run.call_args.kwargs == {"dry_run": True}
    http.post("/feed_items/expire_saved")
    assert run.call_args.kwargs == {"dry_run": False}


def test_item_dict_carries_the_expiry_only_for_saved_items(monkeypatch):
    monkeypatch.setattr(feed_routes, "get_scoped_session", MagicMock())
    monkeypatch.setattr(app_settings, "get_setting", lambda *_: None)
    full = SimpleNamespace(
        id=1, feed_source_id=1, url="u", canonical_url="u", title="t", summary=None, published_at=None, status="saved_for_later",
        saved_at=dt.datetime(2026, 7, 27, tzinfo=UTC), saved_by_user_id=None, document_id=None, review_note=None, review_reason=None,
        ignored_pattern=None, first_seen_at=None,
        llm_discussion_status=None, llm_discussion_at=None, llm_discussion_done_at=None, llm_discussion_result=None,
        group_memberships=[SimpleNamespace(source="manual", group=SimpleNamespace(id=1, name="Może kiedyś", kind="priority", priority_rank=100, retention_months=None, archived_at=None))],
    )
    for built in (feed_routes._item_dict(full), feed_routes._item_dict(full, 6)):  # default looked up, or passed in
        assert built["groups"][0]["name"] == "Może kiedyś"
        assert (built["expires_at"], built["retention_months"]) == ("2027-01-27T00:00:00+00:00", 6)
    full.status = "new"
    assert "expires_at" not in feed_routes._item_dict(full)
