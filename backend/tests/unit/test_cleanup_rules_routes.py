"""Kontrakt HTTP reguł czyszczenia z sesją zastąpioną atrapą."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("flask")

import flask

from library import cleanup_rules_routes as routes
from library.db.models import CleanupRule, DocumentRemovedLine


@pytest.fixture
def api(monkeypatch):
    app = flask.Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(routes.bp)

    @app.before_request
    def auth():
        flask.g.auth = SimpleNamespace(kind=flask.request.headers.get("X-Kind", "service"), key_name="test-key")

    session = MagicMock()
    session.get.return_value = None
    session.flush.side_effect = lambda: setattr(session.add.call_args.args[0], "id", 42)
    monkeypatch.setattr(routes, "get_scoped_session", lambda: session)
    bust = MagicMock()
    monkeypatch.setattr(routes, "bust_cache", bust)
    return app.test_client(), session, bust


def payload(**overrides):
    return dict(scope="global", match_type="literal_line", pattern="Zajrzyj na nasz profil", **overrides)


@pytest.mark.parametrize("kind", ["user", "read_only", ""])
@pytest.mark.parametrize("method,path", [("post", "/cleanup_rules"), ("patch", "/cleanup_rules/42"),
                                         ("delete", "/cleanup_rules/42")])
def test_writes_service_only(api, kind, method, path):
    client, session, bust = api
    assert getattr(client, method)(path, json=payload(), headers={"X-Kind": kind}).status_code == 403
    session.add.assert_not_called()
    session.commit.assert_not_called()
    bust.assert_not_called()


def test_post_bad_regex(api):
    client, session, bust = api
    response = client.post("/cleanup_rules", json={"scope": "global", "match_type": "regex", "pattern": ".*"})
    assert response.status_code == 400
    session.add.assert_not_called()
    bust.assert_not_called()


def test_post_promotes_source_atomically(api):
    client, session, bust = api
    source = DocumentRemovedLine(id=7, review_status="pending")
    session.get.return_value = source
    response = client.post("/cleanup_rules", json=payload(source_removed_line_id=7))
    assert response.status_code == 201
    result = response.get_json()["rule"]
    assert result["id"] == 42
    assert result["source_removed_line_id"] == 7
    assert result["created_by"] == "test-key"
    assert result["hit_count"] == 0
    assert source.review_status == "rule_added"
    assert source.rule_reference == "cleanup_rules:42"
    assert source.reviewed_at is not None
    session.commit.assert_called_once()
    bust.assert_called_once()


def test_missing_source_does_not_insert_dangling_fk(api):
    client, session, _ = api
    response = client.post("/cleanup_rules", json=payload(source_removed_line_id=999))
    assert response.status_code == 201
    assert session.add.call_args.args[0].source_removed_line_id is None


def test_get_filters_and_audit_for_read_only(api):
    client, session, _ = api
    session.scalars.return_value.all.return_value = [CleanupRule(id=42, **payload(), hit_count=3)]
    response = client.get("/cleanup_rules?active=1&scope=global&domain=www.onet.pl", headers={"X-Kind": "read_only"})
    assert response.status_code == 200
    assert response.get_json()["rules"][0]["hit_count"] == 3
    query = session.scalars.call_args.args[0]
    assert query.compile().params == {"scope_1": "global", "domain_1": "onet.pl"}
    assert "cleanup_rules.active IS true" in str(query)


def test_patch_revalidates_and_can_disable_bad_regex(api):
    client, session, bust = api
    rule = CleanupRule(id=42, **payload(), active=True)
    session.get.return_value = rule
    response = client.patch("/cleanup_rules/42", json={"match_type": "regex", "pattern": ".*"})
    assert response.status_code == 400
    assert rule.match_type == "literal_line"
    session.commit.assert_not_called()
    rule.match_type, rule.pattern = "regex", ".*"
    assert client.patch("/cleanup_rules/42", json={"active": False, "note": "Wyłączona"}).status_code == 200
    assert rule.active is False
    bust.assert_called_once()


def test_patch_domain_and_delete(api):
    client, session, bust = api
    rule = CleanupRule(id=42, **payload())
    session.get.return_value = rule
    assert client.patch("/cleanup_rules/42", json={"scope": "domain", "domain": "www.onet.pl"}).status_code == 200
    assert rule.domain == "onet.pl"
    assert client.delete("/cleanup_rules/42").status_code == 200
    session.delete.assert_called_once_with(rule)
    assert bust.call_count == 2


@pytest.mark.parametrize("method", ["patch", "delete"])
def test_unknown_rule(api, method):
    client, _, _ = api
    assert getattr(client, method)("/cleanup_rules/999", json={}).status_code == 404


def test_failed_commit_rolls_back_without_cache_bust(api):
    client, session, bust = api
    session.commit.side_effect = RuntimeError("brak DB")
    with pytest.raises(RuntimeError):
        client.post("/cleanup_rules", json=payload())
    session.rollback.assert_called_once()
    bust.assert_not_called()
