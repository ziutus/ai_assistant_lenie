"""A study mistaken for a world event becomes an information source (timeline filter, conversion, bulk review).

In-memory SQLite like the world-events registry tests; what SQLite cannot check is not needed here.
"""

import json
from types import SimpleNamespace

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("flask")

from flask import Flask
from sqlalchemy import Integer, String, Text, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from library import document_event_sources as des
from library import geopolitics_service as svc
from library import timeline_events
from library import world_events_routes as we_routes
from library import world_events_service as world
from library.db.engine import Base
from library.db.models import (
    DocumentEvent,
    DocumentInformationSource,
    GeoEvent,
    InformationSource,
    InformationSourceAlias,
)
from library.geopolitics_service import GeopoliticsError
from tests.unit.geo_sqlite_support import add_document_event, add_organization, create_schema, make_engine

TOWERS = (
    "Badanie Sherry Towers i współautorów na temat efektu zarażania przemocą po masowych atakach "
    "z użyciem broni palnej w Stanach Zjednoczonych."
)


class _StubBase(DeclarativeBase):
    pass


class StubDocument(_StubBase):
    __tablename__ = "stub_documents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(100), default="t")
    text_md: Mapped[str | None] = mapped_column(Text)


@pytest.fixture
def session(monkeypatch):
    engine = make_engine()
    create_schema(engine)
    Base.metadata.create_all(
        engine,
        tables=[InformationSource.__table__, InformationSourceAlias.__table__, DocumentInformationSource.__table__],
    )
    _StubBase.metadata.create_all(engine)
    monkeypatch.setattr(svc, "Document", StubDocument)
    monkeypatch.setattr(world, "Document", StubDocument)
    s = sessionmaker(bind=engine)()
    for doc_id in (1, 2):
        s.add(StubDocument(id=doc_id, title=f"Dokument {doc_id}", text_md="x"))
    add_organization(s, 1, "WHO")
    s.commit()
    yield s
    s.close()


@pytest.fixture
def client(session, monkeypatch):
    monkeypatch.setattr(we_routes, "get_scoped_session", lambda: session)
    app = Flask(__name__)
    app.register_blueprint(we_routes.bp)
    return app.test_client()


# --- the filter ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("text", [
    TOWERS,
    "W 2015 roku opublikowano badanie o masowych strzelaninach w USA.",
    "W 2020 roku badanie opublikowane w Nature wykazało wzrost zachorowań.",
    "Ukazała się książka Kowalskiego o historii Kaszub.",
    "Artykuł naukowy z 2012 roku dotyczy zarażania przemocą.",
])
def test_publication_statements_are_recognized(text):
    assert timeline_events.is_publication_statement(text)


@pytest.mark.parametrize("text", [
    "Po opublikowaniu badania wybuchły protesty w Waszyngtonie.",
    "Ostrzelano szkołę w Parkland, zginęło 17 osób.",
    "W 2019 roku opublikowano raport Muellera, co wywołało debatę o impeachmencie.",
    "Premier podał się do dymisji po publikacji raportu.",
    "Strzelanina w Las Vegas w 2017 roku była największą w historii USA.",
    "",
])
def test_events_that_merely_mention_a_publication_are_kept(text):
    assert not timeline_events.is_publication_statement(text)


def test_prompt_tells_the_model_a_publication_is_not_an_event():
    prompt = timeline_events._timeline_prompt("Fragment tekstu.")

    assert "Nie wyodrębniaj publikacji jako wydarzeń" in prompt
    assert "opublikowano badanie" in prompt


def test_a_publication_the_model_returns_anyway_is_dropped_and_counted(monkeypatch):
    fragment = f"{TOWERS} W 2018 roku w Parkland zginęło 17 osób."
    raw = json.dumps([
        {"date_text": "2015", "description": TOWERS, "quote": TOWERS},
        {"date_text": "2018", "description": "W Parkland zginęło 17 osób.",
         "quote": "W 2018 roku w Parkland zginęło 17 osób."},
    ])
    usage = SimpleNamespace(
        usage_log_id=1, total_tokens=1,
        cost=SimpleNamespace(total_cost=None, currency=None, status=SimpleNamespace(value="unknown")),
    )
    monkeypatch.setattr(
        timeline_events, "ai_ask", lambda *_a, **_k: SimpleNamespace(response_text=raw, usage=usage),
    )

    events, report = timeline_events.extract_fragment_events(fragment, 1, "model")

    assert [event["description"] for event in events] == ["W Parkland zginęło 17 osób."]
    assert report["rejected_publication"] == 1


# --- one timeline entry -> an information source ------------------------------------------------------------


def test_a_timeline_entry_becomes_an_approved_source_and_leaves_the_timeline(session):
    add_document_event(session, 10, 1, TOWERS, "2015-01-01", precision="year")
    session.commit()

    result = des.convert_document_event_to_source(session, 10, name="Towers i in. (2015)")
    session.commit()

    assert result["created"] and result["source_type"] == "study" and result["role"] == "cited"
    assert session.get(DocumentEvent, 10) is None
    source = session.scalar(select(InformationSource))
    assert (source.canonical_name, source.source_type) == ("Towers i in. (2015)", "study")
    link = session.scalar(select(DocumentInformationSource))
    assert (link.document_id, link.review_status, link.extraction_method) == (1, "approved", "manual_from_event")
    assert link.evidence_excerpt == TOWERS


def test_the_name_defaults_to_the_wording_cut_at_a_word(session):
    add_document_event(session, 10, 1, TOWERS, "2015-01-01", precision="year")
    session.commit()

    result = des.convert_document_event_to_source(session, 10)

    assert result["name"].startswith("Badanie Sherry Towers")
    assert len(result["name"]) <= 120 and not result["name"].endswith(".")


def test_the_same_study_cited_in_another_document_reuses_the_source(session):
    add_document_event(session, 10, 1, TOWERS, "2015-01-01", precision="year")
    add_document_event(session, 11, 2, TOWERS, "2015-01-01", precision="year")
    session.commit()

    des.convert_document_event_to_source(session, 10, name="Towers 2015")
    des.convert_document_event_to_source(session, 11, name="towers 2015")
    session.commit()

    assert len(session.scalars(select(InformationSource)).all()) == 1
    assert len(session.scalars(select(DocumentInformationSource)).all()) == 2


def test_an_entry_that_backs_a_registry_event_is_not_converted(session):
    add_document_event(session, 10, 1, TOWERS, "2015-01-01", precision="year")
    session.commit()
    event, _ = world.promote_document_event(session, 10)
    session.commit()

    with pytest.raises(GeopoliticsError) as error:
        des.convert_document_event_to_source(session, 10)

    assert error.value.status == 409 and f"#{event.id}" in error.value.message
    assert session.get(DocumentEvent, 10) is not None


@pytest.mark.parametrize("kwargs", [
    {"name": "x" * 201},
    {"source_type": "podcast"},
    {"role": "publisher"},
])
def test_bad_input_is_rejected_before_anything_changes(session, kwargs):
    add_document_event(session, 10, 1, TOWERS, "2015-01-01", precision="year")
    session.commit()

    with pytest.raises(GeopoliticsError) as error:
        des.convert_document_event_to_source(session, 10, **kwargs)

    assert error.value.status == 400
    assert session.get(DocumentEvent, 10) is not None
    assert session.scalar(select(InformationSource)) is None


def test_an_unknown_entry_is_404(session):
    with pytest.raises(GeopoliticsError) as error:
        des.convert_document_event_to_source(session, 999)

    assert error.value.status == 404


def test_endpoint_converts_and_answers_201(client, session):
    add_document_event(session, 10, 1, TOWERS, "2015-01-01", precision="year")
    session.commit()

    response = client.post("/document_events/10/to_information_source", json={"name": "Towers 2015"})

    assert response.status_code == 201
    body = response.get_json()
    assert body["status"] == "success" and body["name"] == "Towers 2015" and body["document_id"] == 1
    assert client.post("/document_events/10/to_information_source", json={}).status_code == 404


# --- the bulk review ----------------------------------------------------------------------------------------


def _registry_event(session, title, *, participants=None):
    event, _ = svc.create_event(
        session, title=title, participants=participants, source={"document_id": 1, "quote": title},
    )
    session.commit()
    return event


def test_dry_run_lists_and_changes_nothing(session):
    add_document_event(session, 10, 1, TOWERS, "2015-01-01", precision="year")
    add_document_event(session, 11, 1, "Strzelanina w Parkland, zginęło 17 osób.", "2018-02-14")
    event = _registry_event(session, "Badanie Towers o zarażaniu przemocą dotyczy masowych strzelanin")
    session.commit()

    report = des.review_publication_entries(session, apply=False)
    session.rollback()

    assert [item["document_event_id"] for item in report["timeline"]] == [10]
    assert [item["event_id"] for item in report["registry"]] == [event.id]
    assert session.get(DocumentEvent, 10) is not None
    assert session.get(GeoEvent, event.id).status == "proposed"
    assert session.scalar(select(InformationSource)) is None


def test_apply_converts_timeline_entries_and_rejects_the_registry_event(session):
    add_document_event(session, 10, 1, TOWERS, "2015-01-01", precision="year")
    event = _registry_event(session, "Badanie Towers o zarażaniu przemocą dotyczy masowych strzelanin")
    session.commit()

    report = des.review_publication_entries(session, apply=True)
    session.commit()

    assert report["applied"] and "error" not in report["timeline"][0] and "error" not in report["registry"][0]
    assert session.get(DocumentEvent, 10) is None
    assert session.get(GeoEvent, event.id).status == "rejected"
    links = session.scalars(select(DocumentInformationSource)).all()
    assert len(links) == 2 and all(link.review_status == "approved" for link in links)


def test_a_registry_event_with_participants_or_another_status_is_only_listed(session):
    with_org = _registry_event(
        session, "Badanie WHO o szczepieniach dotyczy odporności",
        participants=[{"type": "organization", "ref": 1, "role": "actor"}],
    )
    confirmed = _registry_event(session, "Badanie Kowalskiego o hałasie dotyczy miast")
    confirmed.status = "confirmed"
    session.commit()

    report = des.review_publication_entries(session, apply=True)
    session.commit()

    assert report["registry"] == []
    reasons = {item["event_id"]: item["skipped"] for item in report["skipped"]}
    assert reasons[with_org.id] == "ma uczestników"
    assert reasons[confirmed.id] == "status confirmed"
    assert session.get(GeoEvent, with_org.id).status == "proposed"
    assert session.scalar(select(InformationSource)) is None
