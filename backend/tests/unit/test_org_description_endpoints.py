"""Organization description proposal: prompt preview, model allowlist, custom prompt, honest statuses."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("sqlalchemy")

import server  # noqa: E402
from tests.unit.test_flask_endpoints_entities import API_HEADERS  # noqa: E402,F401

TEXT = "## Wstęp\n\nPowitanie.\n\n## Energetyka\n\nEDF to francuski operator. EDF zarządza elektrowniami.\n"


@pytest.fixture
def client():
    server.app.config["TESTING"] = True
    with server.app.test_client() as test_client:
        yield test_client


def _session(entity_type="orgName"):
    entity = SimpleNamespace(id=7, document_id=3, entity_type=entity_type, entity_text="EDF", variants=[])
    document = SimpleNamespace(text_md=TEXT, text=TEXT, title="Dok")
    session = MagicMock()
    session.get.side_effect = lambda model, key: entity if key == 7 else document
    return session


def test_preview_returns_prompt_and_models_without_calling_the_llm(client):
    with patch("server.get_scoped_session", return_value=_session()), \
            patch("library.ai.ai_ask") as ask:
        response = client.post("/website_entities/7/describe/preview", json={}, headers=API_HEADERS)
    assert response.status_code == 200
    data = response.get_json()
    assert "„EDF”" in data["prompt"] and data["chapter_title"] == "Energetyka"
    assert data["models"] and data["default_model"]
    ask.assert_not_called()


def test_preview_is_only_for_organizations(client):
    with patch("server.get_scoped_session", return_value=_session("persName")):
        response = client.post("/website_entities/7/describe/preview", json={}, headers=API_HEADERS)
    assert response.status_code == 400


def test_describe_rejects_a_model_outside_the_allowlist(client):
    with patch("server.get_scoped_session", return_value=_session()), patch("library.ai.ai_ask") as ask:
        response = client.post("/website_entities/7/describe", json={"model": "evil/model"}, headers=API_HEADERS)
    assert response.status_code == 400
    ask.assert_not_called()


def test_describe_rejects_a_prompt_that_is_too_long(client):
    with patch("server.get_scoped_session", return_value=_session()), patch("library.ai.ai_ask") as ask:
        response = client.post("/website_entities/7/describe", json={"prompt": "x" * 16001}, headers=API_HEADERS)
    assert response.status_code == 400
    ask.assert_not_called()


def test_describe_sends_the_custom_prompt_and_model_verbatim(client):
    reply = SimpleNamespace(response_text="Francuski operator energetyczny.")
    with patch("server.get_scoped_session", return_value=_session()), \
            patch("library.ai.ai_ask", return_value=reply) as ask:
        response = client.post("/website_entities/7/describe",
                               json={"model": "gpt-4o-mini", "prompt": "Mój prompt"}, headers=API_HEADERS)
    data = response.get_json()
    assert response.status_code == 200 and data["result_status"] == "ok" and data["model"] == "gpt-4o-mini"
    assert ask.call_args.args[0] == "Mój prompt" and ask.call_args.kwargs["model"] == "gpt-4o-mini"


def test_describe_reports_a_model_failure_apart_from_brak(client):
    with patch("server.get_scoped_session", return_value=_session()), \
            patch("library.ai.ai_ask", side_effect=RuntimeError("down")):
        failed = client.post("/website_entities/7/describe", json={}, headers=API_HEADERS).get_json()
    with patch("server.get_scoped_session", return_value=_session()), \
            patch("library.ai.ai_ask", return_value=SimpleNamespace(response_text="BRAK")):
        brak = client.post("/website_entities/7/describe", json={}, headers=API_HEADERS).get_json()
    assert failed["result_status"] == "error" and failed["error_code"] == "RuntimeError"
    assert brak["result_status"] == "insufficient_context"
