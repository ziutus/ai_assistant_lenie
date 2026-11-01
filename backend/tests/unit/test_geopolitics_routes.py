"""HTTP-level tests for library/geopolitics_routes.py (Flask test client, in-memory SQLite)."""

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("flask")

from flask import Flask
from sqlalchemy import Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

from library import geopolitics_routes as routes
from library import geopolitics_service as svc
from library.db.engine import Base
from library.db.models import (
    Country,
    CountryRelationAssessment,
    CountryRelationEvidence,
    GeoEvent,
    GeoEventParticipant,
    GeoEventSource,
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
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(
        engine,
        tables=[
            Country.__table__,
            GeoEvent.__table__,
            GeoEventParticipant.__table__,
            GeoEventSource.__table__,
            CountryRelationAssessment.__table__,
            CountryRelationEvidence.__table__,
        ],
    )
    _StubBase.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    for slug, name, code in [("brazylia", "Brazylia", "BRA"), ("stany-zjednoczone", "Stany Zjednoczone", "USA")]:
        session.add(Country(slug=slug, name_pl=name, iso3=code, map_code=code))
    session.add(StubDocument(id=1, text_md="x"))
    session.commit()
    monkeypatch.setattr(routes, "get_scoped_session", lambda: session)
    monkeypatch.setattr(svc, "Document", StubDocument)
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


def test_event_requires_participants_and_valid_source(client):
    assert client.post("/geo_events", json={"title": "x", "event_date": "2026"}).status_code == 400
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
