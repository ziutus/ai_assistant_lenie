"""HTTP-level tests for library/geopolitics_routes.py (Flask test client, in-memory SQLite)."""

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("flask")

from flask import Flask
from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from library import geopolitics_routes as routes
from library import geopolitics_service as svc
from tests.unit.geo_sqlite_support import create_schema, make_engine
from library.db.models import (
    Country,
)


class _StubBase(DeclarativeBase):
    pass


class StubDocument(_StubBase):
    __tablename__ = "stub_documents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(100), default="t")
    text_md: Mapped[str | None] = mapped_column(Text)


@pytest.fixture
def client(monkeypatch):
    engine = make_engine()
    create_schema(engine)
    _StubBase.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    for slug, name, code in [("brazylia", "Brazylia", "BRA"), ("stany-zjednoczone", "Stany Zjednoczone", "USA")]:
        session.add(Country(slug=slug, name_pl=name, iso3=code, map_code=code))
    session.add(StubDocument(id=1, text_md="x"))
    session.commit()
    monkeypatch.setattr(routes, "get_scoped_session", lambda: session)
    monkeypatch.setattr(svc, "Document", StubDocument)
    store: dict = {}
    from library import app_settings

    monkeypatch.setattr(app_settings, "get_setting", lambda s, key, default=None: store.get(key, default))
    monkeypatch.setattr(
        app_settings,
        "set_setting",
        lambda s, key, value: store.pop(key, None) if value is None else store.__setitem__(key, value),
    )
    app = Flask(__name__)
    app.register_blueprint(routes.bp)
    yield app.test_client()
    session.close()


def _relation(client, **over):
    body = {"from": "brazylia", "to": "stany-zjednoczone", "axis": "political", "score": -1, "valid_from": "2026-03-10"}
    body.update(over)
    return client.post("/country_relations", json=body)


def test_countries_and_axes(client):
    countries = client.get("/countries").get_json()["countries"]
    assert [c["slug"] for c in countries] == ["brazylia", "stany-zjednoczone"]
    axes = client.get("/geopolitics/axes").get_json()["axes"]
    assert {a["value"] for a in axes} == {"political", "security"}
    assert set(axes[0]["scale"]) == {"-2", "-1", "0", "1", "2"}


def test_proposal_lifecycle_through_http(client):
    created = _relation(client)
    assert created.status_code == 201
    row = created.get_json()["assessment"]
    assert row["status"] == "proposed" and row["version"] == 1

    # not on the map yet
    empty = client.get("/country_relations?country=brazylia&at=2026-06-01")
    assert empty.get_json()["relations"] == []

    proposals = client.get("/geopolitics/proposals").get_json()["proposals"]
    assert [p["id"] for p in proposals] == [row["id"]]

    decided = client.post(
        f"/geopolitics/proposals/{row['id']}/decision", json={"decision": "approve", "expected_version": 1}
    )
    assert decided.status_code == 200 and decided.get_json()["assessment"]["status"] == "confirmed"

    shown = client.get("/country_relations?country=brazylia&at=2026-06-01").get_json()
    assert [r["score"] for r in shown["relations"]] == [-1]
    assert shown["country"]["map_code"] == "BRA"
    reverse = client.get("/country_relations?country=brazylia&at=2026-06-01&direction=to").get_json()
    assert reverse["relations"] == []
    assert client.get(f"/country_relations/{row['id']}/history").get_json()["history"][0]["id"] == row["id"]


def test_decision_with_stale_version_is_409(client):
    row = _relation(client).get_json()["assessment"]
    stale = client.post(
        f"/geopolitics/proposals/{row['id']}/decision", json={"decision": "approve", "expected_version": 9}
    )
    assert stale.status_code == 409


def test_validation_errors_are_400_and_unknown_ids_404(client):
    assert _relation(client, score=7).status_code == 400
    assert _relation(client, axis="cultural").status_code == 400
    assert _relation(client, to="brazylia").status_code == 400
    assert _relation(client, to="atlantyda").status_code == 404
    assert client.post("/geopolitics/proposals/999/decision", json={"decision": "approve"}).status_code == 404
    assert client.get("/country_relations").status_code == 400
    assert client.get("/country_relations?country=brazylia&at=jutro").status_code == 400
    assert client.get("/country_relations?country=atlantyda").status_code == 404
    assert client.patch("/geo_events/999", json={"status": "confirmed"}).status_code == 404


def test_manual_event_with_source_and_status_change(client):
    body = {
        "title": "Ucieczka",
        "event_date": "2026-03-10",
        "participants": [{"country": "brazylia", "role": "actor"}, {"country": "stany-zjednoczone", "role": "target"}],
        "source": {"document_id": 1, "quote": "x cytat"},
    }
    first = client.post("/geo_events", json=body)
    assert first.status_code == 201
    event = first.get_json()["event"]
    assert event["status"] == "proposed" and event["sources"][0]["document_id"] == 1
    again = client.post("/geo_events", json=body)
    assert again.status_code == 200 and again.get_json()["created"] is False

    patched = client.patch(f"/geo_events/{event['id']}", json={"status": "confirmed"})
    assert patched.get_json()["event"]["status"] == "confirmed"
    assert client.patch(f"/geo_events/{event['id']}", json={"status": "weird"}).status_code == 400

    listing = client.get("/geo_events?status=confirmed&country=brazylia").get_json()
    assert listing["total"] == 1
    assert client.get("/geo_events?status=weird").status_code == 400


def test_event_needs_a_title_and_a_valid_source_but_no_country(client):
    assert client.post("/geo_events", json={"event_date": "2026"}).status_code == 400
    assert client.post("/geo_events", json={"title": "x", "event_date": "2026"}).status_code == 201
    bad_doc = {
        "title": "x",
        "event_date": "2026",
        "participants": [{"country": "brazylia", "role": "actor"}],
        "source": {"document_id": 404, "quote": "cos"},
    }
    assert client.post("/geo_events", json=bad_doc).status_code == 404


def test_detect_rejects_unavailable_model_and_hides_provider_errors(client, monkeypatch):
    import library.llm_model_registry as registry

    monkeypatch.setattr(registry, "is_selectable", lambda model, task="organization_description": False)
    assert client.post("/document/1/geopolitics/detect", json={"model": "nope"}).status_code == 400

    monkeypatch.setattr(registry, "is_selectable", lambda model, task="organization_description": True)

    def boom(*args, **kwargs):
        raise RuntimeError("secret provider detail")

    import library.geopolitics_detect as detect

    monkeypatch.setattr(detect, "detect_for_document", boom)
    response = client.post("/document/1/geopolitics/detect", json={"model": "ok"})
    assert response.status_code == 503 and "secret" not in response.get_data(as_text=True)


MODELS = [
    {
        "id": "Bielik-11B-v3.0-Instruct",
        "label": "Bielik",
        "available": True,
        "external": False,
        "input_price_per_million": "0.2",
        "output_price_per_million": "0.4",
        "currency": "USD",
    },
    {
        "id": "openrouter/x/y",
        "label": "Y",
        "available": True,
        "external": True,
        "input_price_per_million": "0.1",
        "output_price_per_million": "0.3",
        "currency": "USD",
    },
]


def _registry(monkeypatch):
    import library.llm_model_registry as registry

    seen = []

    def selectable(task="organization_description"):
        seen.append(task)
        return MODELS

    monkeypatch.setattr(registry, "selectable_models", selectable)
    monkeypatch.setattr(
        registry, "is_selectable", lambda model, task="organization_description": any(m["id"] == model for m in MODELS)
    )
    return seen


def test_model_list_has_prices_and_uses_its_own_task(client, monkeypatch):
    seen = _registry(monkeypatch)
    body = client.get("/geopolitics/model").get_json()
    assert seen == ["geopolitics"]
    assert body["default_model"] == "Bielik-11B-v3.0-Instruct" and body["saved"] is False
    assert body["models"][1]["input_price_per_million"] == "0.1"


def test_default_model_can_be_saved_and_cleared(client, monkeypatch):
    _registry(monkeypatch)
    saved = client.put("/geopolitics/model", json={"model": "openrouter/x/y"}).get_json()
    assert saved["default_model"] == "openrouter/x/y" and saved["saved"] is True
    assert client.get("/geopolitics/model").get_json()["default_model"] == "openrouter/x/y"
    cleared = client.put("/geopolitics/model", json={"model": None}).get_json()
    assert cleared["default_model"] == "Bielik-11B-v3.0-Instruct" and cleared["saved"] is False


def test_unknown_model_cannot_be_saved(client, monkeypatch):
    _registry(monkeypatch)
    assert client.put("/geopolitics/model", json={"model": "nope"}).status_code == 400
    assert client.put("/geopolitics/model", json={}).status_code == 400


def test_a_saved_model_that_became_unavailable_falls_back(client, monkeypatch):
    _registry(monkeypatch)
    client.put("/geopolitics/model", json={"model": "openrouter/x/y"})
    del MODELS_BACKUP[:]
    MODELS_BACKUP.extend(MODELS)
    MODELS[:] = [MODELS_BACKUP[0]]
    try:
        assert client.get("/geopolitics/model").get_json()["default_model"] == "Bielik-11B-v3.0-Instruct"
    finally:
        MODELS[:] = MODELS_BACKUP


MODELS_BACKUP: list = []


def test_unexpected_failure_is_json_with_the_error_class_and_no_details(client, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(routes, "list_proposals", boom)
    response = client.get("/geopolitics/proposals")
    body = response.get_json()
    assert response.status_code == 500 and body["status"] == "error"
    assert "RuntimeError" in body["message"] and "secret" not in body["message"]


def test_http_errors_keep_their_own_status(client):
    assert client.get("/geopolitics/nonexistent").status_code == 404
