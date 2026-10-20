"""HTTP contract for phrase corrections using mocked persistence."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("flask")

import flask
from sqlalchemy.exc import IntegrityError

from library import transcript_corrections_routes as routes
from library.db.models import Document, TranscriptCorrection
from library.transcript_corrections import TranscriptCorrectionRow

PATTERN = "pi\u0119to Achillesa"
REPLACEMENT = "pi\u0119ta Achillesa"


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

    def commit():
        if session.add.called:
            session.add.call_args.args[0].id = 42

    session.commit.side_effect = commit
    monkeypatch.setattr(routes, "get_scoped_session", lambda: session)
    bust, bump = MagicMock(), MagicMock()
    monkeypatch.setattr(routes, "bust_cache", bust)
    monkeypatch.setattr(routes, "_bump_hit_counts", bump)
    return app.test_client(), session, bust, bump


def payload(**overrides):
    return dict(pattern=PATTERN, replacement=REPLACEMENT) | overrides


@pytest.mark.parametrize("kind", ["user", "read_only", ""])
@pytest.mark.parametrize("method,path", [("patch", "/42"), ("delete", "/42")])
def test_service_only(api, kind, method, path):
    client, session, bust, _ = api
    assert getattr(client, method)("/transcript_corrections" + path, json=payload(),
                                   headers={"X-Kind": kind}).status_code == 403
    session.commit.assert_not_called()
    bust.assert_not_called()


@pytest.mark.parametrize("path", ["", "/apply"])
@pytest.mark.parametrize("kind", ["read_only", ""])
def test_create_and_apply_reject_read_only(api, kind, path):
    client, session, _, _ = api
    assert client.post("/transcript_corrections" + path, json=payload(),
                       headers={"X-Kind": kind}).status_code == 403
    session.commit.assert_not_called()


def test_user_key_may_create_rule(api):
    client, _, bust, _ = api
    assert client.post("/transcript_corrections", json=payload(), headers={"X-Kind": "user"}).status_code == 201
    bust.assert_called_once()


def test_create_defaults_and_audit(api):
    client, session, bust, _ = api
    response = client.post("/transcript_corrections", json=payload())
    assert response.status_code == 201
    rule = response.get_json()["rule"]
    assert rule["id"] == 42 and rule["created_by"] == "test-key"
    assert rule["scope"] == "global" and rule["active"] is True and rule["hit_count"] == 0
    session.commit.assert_called_once()
    bust.assert_called_once()


def test_get_filters(api):
    client, session, _, _ = api
    session.scalars.return_value.all.return_value = [TranscriptCorrection(id=42, **payload(), hit_count=3)]
    response = client.get("/transcript_corrections?active=1&scope=author&author=CHANNEL", headers={"X-Kind": "read_only"})
    assert response.status_code == 200
    assert response.get_json()["rules"][0]["hit_count"] == 3
    query = session.scalars.call_args.args[0]
    assert query.compile().params == {"scope_1": "author", "author_1": "channel"}
    assert "transcript_corrections.active IS true" in str(query)
    assert client.get("/transcript_corrections?active=true").status_code == 400


def test_patch_revalidates_author_disable_delete(api):
    client, session, bust, _ = api
    rule = TranscriptCorrection(id=42, **payload(), scope="global", active=True)
    session.get.return_value = rule
    assert client.patch("/transcript_corrections/42", json={"pattern": "word"}).status_code == 400
    assert rule.pattern == PATTERN
    assert client.patch("/transcript_corrections/42", json={"scope": "author", "author": " CHANNEL "}).status_code == 200
    assert rule.author == "channel"
    assert client.patch("/transcript_corrections/42", json={"active": False}).status_code == 200
    assert rule.active is False
    assert client.delete("/transcript_corrections/42").status_code == 200
    session.delete.assert_called_once_with(rule)
    assert bust.call_count == 3


@pytest.mark.parametrize("method", ["patch", "delete"])
def test_unknown_rule(api, method):
    assert getattr(api[0], method)("/transcript_corrections/999", json={}).status_code == 404


@pytest.mark.parametrize("body", [[], None, {"pattern": "word"}, payload(active=1), payload(note=3)])
def test_invalid_body(api, body):
    client, session, bust, _ = api
    assert client.post("/transcript_corrections", json=body).status_code == 400
    session.commit.assert_not_called()
    bust.assert_not_called()


def test_duplicate_and_failed_commit(api):
    client, session, bust, _ = api
    session.commit.side_effect = IntegrityError("insert", {}, Exception("duplicate"))
    assert client.post("/transcript_corrections", json=payload()).status_code == 409
    session.rollback.assert_called_once()
    bust.assert_not_called()
    session.commit.side_effect = RuntimeError("no DB")
    with pytest.raises(RuntimeError):
        client.post("/transcript_corrections", json=payload())
    assert session.rollback.call_count == 2


@pytest.mark.parametrize("dry_run", [True, False])
def test_apply_dry_run_vs_persist(api, dry_run):
    client, session, bust, bump = api
    doc = Document(id=10872, document_type="youtube", byline="channel", text=PATTERN, text_md="## " + PATTERN)
    session.get.return_value = doc
    session.scalars.return_value = [TranscriptCorrectionRow(42, "global", None, PATTERN, REPLACEMENT)]
    body = {"document_id": 10872}
    if not dry_run:
        body["dry_run"] = False
    response = client.post("/transcript_corrections/apply", json=body)
    assert response.status_code == 200
    result = response.get_json()
    assert result["dry_run"] is dry_run
    assert result["hits"] == [{"rule_id": 42, "count": 2}]
    assert result["fields"]["text"]["snippet"] == {"before": PATTERN, "after": REPLACEMENT}
    assert doc.text == (PATTERN if dry_run else REPLACEMENT)
    assert doc.text_md == "## " + (PATTERN if dry_run else REPLACEMENT)
    bust.assert_not_called()
    if dry_run:
        session.commit.assert_not_called()
        session.execute.assert_not_called()
        bump.assert_not_called()
    else:
        session.commit.assert_called_once()
        bump.assert_called_once_with([(42, 2)])


def test_apply_missing_md_no_match(api):
    client, session, _, bump = api
    session.get.return_value = Document(id=1, text="unchanged", text_md=None)
    session.scalars.return_value = []
    result = client.post("/transcript_corrections/apply", json={"document_id": 1}).get_json()
    assert result["hits"] == [] and "text_md" not in result["fields"]
    assert result["fields"]["text"]["snippet"] is None
    bump.assert_not_called()


@pytest.mark.parametrize("body", [{}, {"document_id": "all"}, {"document_id": True}, {"document_id": 0},
                                  {"document_id": 1, "dry_run": "false"}])
def test_apply_rejects_invalid_or_bulk_request(api, body):
    assert api[0].post("/transcript_corrections/apply", json=body).status_code == 400


def test_apply_unknown_document(api):
    assert api[0].post("/transcript_corrections/apply", json={"document_id": 999}).status_code == 404
