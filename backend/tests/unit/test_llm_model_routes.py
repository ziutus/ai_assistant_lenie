"""HTTP contract of /llm_models (ADR-030) with the session replaced by a mock."""

import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("flask")

import flask
from sqlalchemy.exc import IntegrityError

from library import llm_model_routes as routes
from library.db.models import LlmModel


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
    session.scalars.return_value.first.return_value = None
    monkeypatch.setattr(routes, "get_scoped_session", lambda: session)
    invalidate = MagicMock()
    monkeypatch.setattr(routes, "invalidate_cache", invalidate)
    return app.test_client(), session, invalidate


def vertex(**overrides):
    return {"model_id": "gemini-4-flash", "label": "Gemini 4 Flash", "provider": "google-vertexai", **overrides}


def stored(**overrides):
    fields = dict(id=7, model_id="gemini-4-flash", label="Gemini 4 Flash", provider="google-vertexai", external=False,
                  verified=False, status="active", retires_on=None, note=None,
                  created_at=datetime.datetime(2026, 10, 29), updated_at=datetime.datetime(2026, 10, 29))
    return LlmModel(**{**fields, **overrides})


class TestList:
    def test_lists_models_with_iso_dates(self, api):
        client, session, _ = api
        session.scalars.return_value.all.return_value = [stored(retires_on=datetime.date(2027, 1, 2))]
        body = client.get("/llm_models", headers={"X-Kind": "user"}).get_json()
        assert body["models"][0]["model_id"] == "gemini-4-flash" and body["models"][0]["retires_on"] == "2027-01-02"

    def test_unknown_status_filter_is_a_400(self, api):
        assert api[0].get("/llm_models?status=gone").status_code == 400


class TestAdd:
    def test_creates_and_busts_the_cache_with_a_pricing_warning(self, api):
        client, session, invalidate = api
        response = client.post("/llm_models", json=vertex())
        assert response.status_code == 201
        session.add.assert_called_once()
        invalidate.assert_called_once()
        assert "llm_pricing" in response.get_json()["warnings"][0]

    def test_openrouter_model_needs_no_pricing_row(self, api):
        client, _, _ = api
        response = client.post("/llm_models", json=vertex(model_id="openrouter/google/gemma-3-27b-it", provider="openrouter"))
        assert response.status_code == 201 and response.get_json()["warnings"] == []

    def test_needs_a_service_key(self, api):
        client, session, _ = api
        assert client.post("/llm_models", json=vertex(), headers={"X-Kind": "user"}).status_code == 403
        session.add.assert_not_called()

    def test_invalid_row_is_a_400(self, api):
        assert api[0].post("/llm_models", json=vertex(provider="bedrock")).status_code == 400

    def test_duplicate_model_id_is_a_409(self, api):
        client, session, invalidate = api
        session.scalars.return_value.first.return_value = 3
        assert client.post("/llm_models", json=vertex()).status_code == 409
        invalidate.assert_not_called()

    def test_race_on_the_unique_index_is_a_409(self, api):
        client, session, _ = api
        session.commit.side_effect = IntegrityError("x", {}, Exception())
        assert client.post("/llm_models", json=vertex()).status_code == 409
        session.rollback.assert_called_once()

    def test_body_must_be_an_object(self, api):
        assert api[0].post("/llm_models", data="[]", content_type="application/json").status_code == 400


class TestPatch:
    def test_retiring_a_model_is_one_patch(self, api):
        client, session, invalidate = api
        model = stored(model_id="openrouter/google/gemini-2.5-flash-lite", provider="openrouter", status="deprecated")
        session.get.return_value = model
        response = client.patch("/llm_models/7", json={"status": "retired", "note": "Przestał działać"})
        assert response.status_code == 200 and model.status == "retired" and model.note == "Przestał działać"
        invalidate.assert_called_once()

    def test_unknown_model_is_a_404(self, api):
        assert api[0].patch("/llm_models/99", json={"status": "retired"}).status_code == 404

    def test_identity_fields_are_immutable(self, api):
        client, session, _ = api
        session.get.return_value = stored()
        assert client.patch("/llm_models/7", json={"provider": "openai"}).status_code == 400
        assert client.patch("/llm_models/7", json={"model_id": "other"}).status_code == 400

    def test_invalid_status_is_a_400_and_changes_nothing(self, api):
        client, session, invalidate = api
        model = stored()
        session.get.return_value = model
        assert client.patch("/llm_models/7", json={"status": "gone"}).status_code == 400
        assert model.status == "active"
        invalidate.assert_not_called()

    def test_needs_a_service_key(self, api):
        assert api[0].patch("/llm_models/7", json={"status": "retired"}, headers={"X-Kind": "user"}).status_code == 403


class TestDelete:
    def test_deletes_and_busts_the_cache(self, api):
        client, session, invalidate = api
        session.get.return_value = stored()
        assert client.delete("/llm_models/7").status_code == 200
        session.delete.assert_called_once()
        invalidate.assert_called_once()

    def test_unknown_model_is_a_404(self, api):
        assert api[0].delete("/llm_models/99").status_code == 404
