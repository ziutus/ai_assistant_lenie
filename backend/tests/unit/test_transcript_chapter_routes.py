"""HTTP chapter suggestion, preview and persistence guards with a mocked database."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from library import chunk_review_routes as routes
from library import transcript_chapter_suggester as s


@pytest.fixture
def client(monkeypatch):
    session = MagicMock()
    session.get.return_value = SimpleNamespace(document_type="youtube", text="Pierwsze. Drugie. Trzecie.",
                                             text_md="Original markdown", chapter_types=["SZUM"])
    session.scalar.return_value = None
    monkeypatch.setattr(routes, "get_scoped_session", lambda: session)
    monkeypatch.setattr(routes, "_chapter_boundary_run_count", lambda *args: 2)
    monkeypatch.setattr(s, "default_model", lambda session: "test")
    monkeypatch.setattr(s.llm_model_registry, "is_selectable", lambda model, task: model == "test")
    monkeypatch.setattr(s.llm_model_registry, "selectable_models", lambda task: [
        {"id": "test", "context_length": 10000, "max_output_tokens": 1000}])
    app = Flask(__name__)
    app.register_blueprint(routes.bp)
    with patch("library.document_editing.document_has_embeddings", return_value=False):
        client = app.test_client()
        client.session = session
        yield client


def test_dry_run_no_model_call(client):
    with patch("library.ai.ai_ask") as ask:
        response = client.post("/document/1/suggest_chapters", json={"dry_run": True})
    assert response.status_code == 200
    data = response.get_json()
    assert data["candidates"]["fits_single_call"] is True
    assert data["candidates"]["sentence_count"] == 3
    assert data["model_context"]["context_length"] == 10000
    ask.assert_not_called()
    client.session.commit.assert_not_called()


def test_suggestion_does_not_store(client):
    with patch.object(s, "suggest_chapters", return_value={"status": "ok", "chapters": []}) as suggest:
        response = client.post("/document/1/suggest_chapters", json={"model": "test"})
    assert response.status_code == 200
    suggest.assert_called_once()
    client.session.commit.assert_not_called()


def test_apply_updates_types_and_preserves_text_md(client):
    doc = client.session.get.return_value
    with patch("library.ai.ai_ask") as ask:
        response = client.post("/document/1/apply_chapters", json={
            "expected_text_sha256": s.text_sha256(doc.text), "chapters": [
                {"start_sentence": 0, "title": "Pierwszy"}, {"start_sentence": 2, "title": "Drugi"}]})
    assert response.status_code == 200
    assert response.get_json()["chapter_count"] == 2
    assert doc.chapter_types == ["TEMAT", "TEMAT"]
    assert doc.text_md == "Original markdown"
    assert "## Drugi\n\nTrzecie." in doc.text
    client.session.commit.assert_called_once()
    ask.assert_not_called()


@pytest.mark.parametrize("operation", ["suggest_chapters", "apply_chapters"])
@pytest.mark.parametrize("guard", ["headings", "active", "embeddings", "type", "empty"])
def test_guards(client, operation, guard):
    doc = client.session.get.return_value
    if guard == "headings":
        doc.text = "## Już jest\nTekst."
    if guard == "active":
        client.session.scalar.return_value = 1
    if guard == "type":
        doc.document_type = "webpage"
    if guard == "empty":
        doc.text = " "
    with patch("library.document_editing.document_has_embeddings", return_value=guard == "embeddings"):
        response = client.post(f"/document/1/{operation}", json={})
    assert response.status_code == (400 if guard in ("type", "empty") else 409)
    client.session.commit.assert_not_called()


def test_hash_conflict(client):
    response = client.post("/document/1/apply_chapters", json={"expected_text_sha256": "old", "chapters": []})
    assert response.status_code == 409
    client.session.commit.assert_not_called()


def test_invalid_model_and_payload(client):
    assert client.post("/document/1/suggest_chapters", json={"model": "evil"}).status_code == 400
    assert client.post("/document/1/suggest_chapters", json=[]).status_code == 400
    assert client.post("/document/1/apply_chapters", json={"chapters": []}).status_code == 400


def test_model_setting(client):
    with (
        patch.object(s.app_settings, "set_setting") as save,
        patch.object(s.app_settings, "get_setting", return_value=None),
    ):
        assert client.get("/transcript_chapters/model").status_code == 200
        assert client.put("/transcript_chapters/model", json={"model": "test"}).status_code == 200
        save.assert_called_with(client.session, s.SETTING_KEY, "test")
        assert client.put("/transcript_chapters/model", json={"model": None}).status_code == 200
        save.assert_called_with(client.session, s.SETTING_KEY, None)
        assert client.put("/transcript_chapters/model", json={"model": "evil"}).status_code == 400
