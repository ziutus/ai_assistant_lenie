"""HTTP contract of PATCH /document/<id>/tags with mocked persistence."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("flask")

import flask  # noqa: E402

from library import document_tags_routes as routes  # noqa: E402
from library.document_tags_routes import apply_tag_changes  # noqa: E402


@pytest.fixture
def api(monkeypatch):
    app = flask.Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(routes.bp)
    state = {"kind": "service"}

    @app.before_request
    def auth():
        flask.g.auth = SimpleNamespace(kind=state["kind"], key_name="test-key")

    doc = SimpleNamespace(id=11263, tags="geopolityka,miejsce-manili,miejsce-manila,kraj-filipiny")
    session = MagicMock()
    session.get.side_effect = lambda model, doc_id: doc if doc_id == 11263 else None
    monkeypatch.setattr(routes, "get_scoped_session", lambda: session)
    return app.test_client(), doc, session, state


def test_remove_one_tag_keeps_the_others(api):
    client, doc, session, _ = api
    response = client.patch("/document/11263/tags", json={"remove": ["miejsce-manili"]})
    assert response.status_code == 200
    body = response.get_json()
    assert body["removed"] == ["miejsce-manili"] and body["added"] == []
    assert doc.tags == "geopolityka,miejsce-manila,kraj-filipiny"
    assert body["tags"] == ["geopolityka", "miejsce-manila", "kraj-filipiny"]
    session.commit.assert_called_once()


def test_add_normalizes_and_does_not_duplicate(api):
    client, doc, _, _ = api
    body = client.patch("/document/11263/tags", json={"add": ["  Kraj-Filipiny ", "Nowy  Tag"]}).get_json()
    assert body["added"] == ["nowy tag"] and body["already_present"] == ["kraj-filipiny"]
    assert doc.tags.endswith(",nowy tag")


def test_remove_ignores_case_and_reports_a_missing_tag(api):
    client, doc, _, _ = api
    body = client.patch("/document/11263/tags", json={"remove": ["GEOPOLITYKA", "nie-ma"]}).get_json()
    assert body["removed"] == ["geopolityka"] and body["not_found"] == ["nie-ma"]
    assert "geopolityka" not in doc.tags.split(",")


def test_nothing_to_change_does_not_commit(api):
    client, _, session, _ = api
    body = client.patch("/document/11263/tags", json={"remove": ["nie-ma"], "add": ["kraj-filipiny"]}).get_json()
    assert body["removed"] == [] and body["added"] == []
    session.commit.assert_not_called()


@pytest.mark.parametrize("payload", [
    {}, {"add": []}, {"add": "tag"}, {"add": [1]}, {"add": ["a,b"]}, {"add": [" "]}, {"add": ["x" * 101]},
    {"add": ["a"], "remove": ["A"]}, {"remove": [str(i) for i in range(51)]},
])
def test_invalid_requests_are_rejected_without_touching_the_document(api, payload):
    client, doc, session, _ = api
    before = doc.tags
    assert client.patch("/document/11263/tags", json=payload).status_code == 400
    assert doc.tags == before
    session.commit.assert_not_called()


@pytest.mark.parametrize("payload,message", [
    ({"add": ["a,b"]}, "Tag nie może zawierać przecinka"),
    ({"add": [" "]}, "Tag nie może być pusty"),
    ({"add": [1]}, "Tag musi być tekstem"),
    ({"add": "tag"}, "add i remove muszą być listami tagów"),
])
def test_validation_answers_a_fixed_text_per_error(api, payload, message):
    """The text is a constant per error code, never built from the exception (CodeQL py/stack-trace-exposure)."""
    body = api[0].patch("/document/11263/tags", json=payload).get_json()
    assert body == {"status": "error", "message": message}


def test_non_object_body_is_rejected(api):
    assert api[0].patch("/document/11263/tags", json=["a"]).status_code == 400


def test_unknown_document_is_404(api):
    assert api[0].patch("/document/1/tags", json={"add": ["a"]}).status_code == 404


def test_read_only_key_is_refused(api):
    client, doc, _, state = api
    state["kind"] = "reader"
    assert client.patch("/document/11263/tags", json={"remove": ["geopolityka"]}).status_code == 403
    assert "geopolityka" in doc.tags


def test_commit_failure_rolls_back_and_answers_500(api):
    client, _, session, _ = api
    session.commit.side_effect = RuntimeError("db")
    assert client.patch("/document/11263/tags", json={"remove": ["geopolityka"]}).status_code == 500
    session.rollback.assert_called_once()


def test_apply_tag_changes_is_pure_and_keeps_original_spelling_of_kept_tags():
    result = apply_tag_changes("A,b,,C", ["c", "d"], ["B"])
    assert result["tags"] == ["A", "C", "d"] and result["removed"] == ["b"] and result["added"] == ["d"]
    assert apply_tag_changes(None, ["x"], []) ["tags"] == ["x"]
