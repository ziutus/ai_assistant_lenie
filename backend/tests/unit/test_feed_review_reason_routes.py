"""HTTP contracts, permissions and deletion races for the reason catalog."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import flask
import pytest
from sqlalchemy.exc import IntegrityError

from library import feed_review_reason_routes as routes
from library.db.models import FeedReviewReason


@pytest.fixture
def api(monkeypatch):
    app = flask.Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(routes.bp)

    @app.before_request
    def auth():
        flask.g.auth = SimpleNamespace(kind=flask.request.headers.get("X-Kind", "service"))

    session = MagicMock()
    session.get.return_value = None
    session.scalar.return_value = 0
    monkeypatch.setattr(routes, "get_scoped_session", lambda: session)
    bust = MagicMock()
    monkeypatch.setattr(routes.store, "bust_cache", bust)
    monkeypatch.setattr(routes.store, "_fetch_rows", lambda: routes.store.SEED_REASONS)
    # Bust the real cache before replacing it in the fixture.
    monkeypatch.setattr(routes.store, "_expires_at", 0)
    return app.test_client(), session, bust


def stored(**overrides):
    return FeedReviewReason(
        **dict(
            {
                "code": "custom",
                "label": "Własny",
                "sort_order": 100,
                "active": True,
                "selectable": True,
                "system": False,
            },
            **overrides,
        )
    )


def test_get_selectable_and_all_usage(api):
    client, session, _ = api
    response = client.get("/feed_review_reasons?selectable=1", headers={"X-Kind": "user"})
    assert response.status_code == 200
    rows = response.json["reasons"]
    assert len(rows) == 6 and all(row["active"] and row["selectable"] for row in rows)
    assert [row["code"] for row in rows][2] == "interesting_no_time"
    session.scalars.return_value.all.return_value = [stored()]
    session.execute.return_value.all.return_value = [("custom", 3)]
    assert client.get("/feed_review_reasons").json["reasons"][0]["usage_count"] == 3


def test_create_and_duplicate(api):
    client, session, bust = api
    response = client.post("/feed_review_reasons", json={"code": "custom", "label": "  Własny  powód "})
    assert response.status_code == 201
    assert response.json["reason"]["label"] == "Własny powód"
    assert response.json["reason"]["system"] is False
    bust.assert_called_once()
    session.get.return_value = stored()
    assert client.post("/feed_review_reasons", json={"code": "custom", "label": "Test"}).status_code == 409


@pytest.mark.parametrize(
    "data", [[], {}, {"code": "BAD", "label": "Test"}, {"code": "test", "label": "Test", "system": True}]
)
def test_create_bad_input(api, data):
    assert api[0].post("/feed_review_reasons", json=data).status_code == 400


@pytest.mark.parametrize("method", ["post", "patch", "delete"])
def test_service_only(api, method):
    path = "/feed_review_reasons" + ("/custom" if method != "post" else "")
    response = getattr(api[0], method)(path, json={}, headers={"X-Kind": "user"})
    assert response.status_code == 403
    assert "service" in response.text
    api[1].commit.assert_not_called()


def test_patch_and_validation(api):
    client, session, bust = api
    row = stored()
    session.get.return_value = row
    assert (
        client.patch(
            "/feed_review_reasons/custom", json={"label": "Nowa", "sort_order": 2, "active": False, "selectable": False}
        ).status_code
        == 200
    )
    assert row.label == "Nowa" and row.sort_order == 2 and not row.active and not row.selectable
    bust.assert_called_once()
    for data in ({"code": "changed"}, {"sort_order": True}, {"active": "false"}, {"unknown": 1}):
        assert client.patch("/feed_review_reasons/custom", json=data).status_code == 400


def test_system_restrictions(api):
    client, session, _ = api
    session.get.return_value = stored(system=True)
    for data in ({"active": True}, {"selectable": False}, {"system": False}):
        assert client.patch("/feed_review_reasons/custom", json=data).status_code == 400
    assert client.patch("/feed_review_reasons/custom", json={"label": "Nowa", "sort_order": 9}).status_code == 200
    assert client.delete("/feed_review_reasons/custom").status_code == 409


def test_delete_usage_and_success(api):
    client, session, bust = api
    session.get.return_value = stored()
    session.scalar.return_value = 1
    assert client.delete("/feed_review_reasons/custom").status_code == 409
    session.delete.assert_not_called()
    session.scalar.return_value = 0
    assert client.delete("/feed_review_reasons/custom").status_code == 200
    bust.assert_called_once()


@pytest.mark.parametrize("method", ["post", "delete"])
def test_integrity_race_rolls_back(api, method):
    client, session, bust = api
    session.commit.side_effect = IntegrityError("sql", {}, Exception())
    if method == "delete":
        session.get.return_value = stored()
        response = client.delete("/feed_review_reasons/custom")
    else:
        response = client.post("/feed_review_reasons", json={"code": "custom", "label": "Test"})
    assert response.status_code == 409
    session.rollback.assert_called_once()
    bust.assert_not_called()


def test_missing_rows(api):
    assert api[0].patch("/feed_review_reasons/missing", json={"label": "Test"}).status_code == 404
    assert api[0].delete("/feed_review_reasons/missing").status_code == 404
