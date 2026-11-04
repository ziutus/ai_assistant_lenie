"""World-events registry (ADR-034): events without country or date, aliases, participants of three kinds,
named-event mention decisions, direct vs context evidence. In-memory SQLite; what SQLite cannot check (partial
unique index, trigram search, foreign-key enforcement) was verified on PostgreSQL when the migration was written.
"""

import importlib.util
import pathlib

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("flask")

from flask import Flask
from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from library import geopolitics_routes as geo_routes
from library import geopolitics_service as svc
from library import world_events_routes as we_routes
from library import world_events_service as world
from library.db.models import (
    Country,
    CountryRelationAssessment,
    CountryRelationEvidence,
    GeoEvent,
    GeoEventMentionLink,
)
from tests.unit.geo_sqlite_support import (
    add_document_event,
    add_event_mention,
    add_organization,
    add_person,
    create_schema,
    make_engine,
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
    _StubBase.metadata.create_all(engine)
    monkeypatch.setattr(svc, "Document", StubDocument)
    monkeypatch.setattr(world, "Document", StubDocument)
    s = sessionmaker(bind=engine)()
    for slug, name, code in [
        ("brazylia", "Brazylia", "BRA"),
        ("stany-zjednoczone", "Stany Zjednoczone", "USA"),
        ("izrael", "Izrael", "ISR"),
    ]:
        s.add(Country(slug=slug, name_pl=name, iso3=code, map_code=code))
    for doc_id in (1, 2, 3, 4):
        s.add(StubDocument(id=doc_id, title=f"Dokument {doc_id}", text_md="x"))
    add_organization(s, 1, "WHO")
    add_organization(s, 2, "CrowdStrike")
    add_organization(s, 3, "Meta")
    add_organization(s, 4, "Meta")
    add_person(s, 1, "Donald Tusk")
    s.commit()
    yield s
    s.close()


@pytest.fixture
def client(session, monkeypatch):
    monkeypatch.setattr(geo_routes, "get_scoped_session", lambda: session)
    monkeypatch.setattr(we_routes, "get_scoped_session", lambda: session)
    app = Flask(__name__)
    app.register_blueprint(geo_routes.bp)
    app.register_blueprint(we_routes.bp)
    return app.test_client()


def make(session, title, **kw):
    event, created = svc.create_event(session, title=title, **kw)
    session.commit()
    return event


# --- names ----------------------------------------------------------------------------------------------------


def test_name_key_keeps_accents_and_search_key_folds_them():
    assert svc.name_key("  Wybory   w  ŁODZI ") == "wybory w łodzi"
    assert svc.name_key("Wybory w Łodzi") != svc.name_key("Wybory w Lodzi")
    assert svc.search_key("Wybory w Łodzi!") == svc.search_key("wybory w lodzi") == "wybory w lodzi"
    assert svc.name_key("é") == svc.name_key("é")  # NFC


def test_dictionaries_match_the_migration_seed():
    path = (
        pathlib.Path(__file__).resolve().parents[2] / "alembic" / "versions" / "c7e2b5a9d814_world_events_registry.py"
    )
    spec = importlib.util.spec_from_file_location("registry_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert dict(module._KINDS) == world.KIND_LABELS
    assert dict(module._ROLES) == world.ROLE_LABELS
    assert tuple(world.KIND_LABELS) == svc.EVENT_KINDS and tuple(world.ROLE_LABELS) == svc.ROLES


# --- events without country, without date ----------------------------------------------------------------------


def test_an_event_needs_neither_a_country_nor_a_date(session):
    event = make(session, "Awaria CrowdStrike", kind="outage")
    data = svc.event_to_dict(event)
    assert data["participants"] == [] and data["event_date"] is None and data["date_precision"] == "unknown"
    assert data["kind"] == "outage" and [a["alias"] for a in data["aliases"]] == ["Awaria CrowdStrike"]


def test_dates_are_validated(session):
    with pytest.raises(svc.GeopoliticsError):
        svc.create_event(session, title="X", event_date_end="2026-01-01")  # an end needs a start
    with pytest.raises(svc.GeopoliticsError):
        svc.create_event(session, title="X", event_date="2026-02-01", event_date_end="2026-01-01")
    with pytest.raises(svc.GeopoliticsError):
        svc.create_event(session, title="X", event_date="2026-02-01", event_date_end="2026-03-01", is_ongoing=True)
    with pytest.raises(svc.GeopoliticsError):
        svc.create_event(session, title="X", kind="nonsense")
    ranged = make(session, "Wybory", event_date="2026-02", event_date_end="2026-03-15", kind="election")
    assert ranged.date_precision == "month" and ranged.end_date_precision == "day"
    ongoing = make(session, "Kampania", event_date="2026-01-01", is_ongoing=True)
    assert ongoing.is_ongoing and ongoing.event_date_end is None


def test_the_same_report_is_one_event_with_more_names(session):
    first = make(session, "Wybory w Izraelu", kind="election", participants=[("izrael", "location")])
    again, created = svc.create_event(
        session,
        title="wybory  w izraelu",
        kind="election",
        participants=[("izrael", "location")],
        aliases=["Wybory do Knesetu"],
    )
    session.commit()
    assert not created and again.id == first.id
    assert {a.alias for a in again.aliases} == {"Wybory w Izraelu", "Wybory do Knesetu"}
    assert session.query(GeoEvent).count() == 1


def test_an_undated_and_a_dated_event_with_one_title_are_different_events(session):
    undated = make(session, "Wybory w Polsce", participants=[("brazylia", "location")])
    dated = make(session, "Wybory w Polsce", event_date="2023-10-15", participants=[("brazylia", "location")])
    assert undated.id != dated.id


def test_two_analyses_racing_for_one_report_end_with_one_event(session, monkeypatch):
    winner = make(session, "Premiera modelu", kind="product_launch")
    real_scalar = session.scalar
    calls = {"n": 0}

    def blind_first_lookup(statement, *args, **kwargs):
        calls["n"] += 1
        return None if calls["n"] == 1 else real_scalar(statement, *args, **kwargs)

    monkeypatch.setattr(session, "scalar", blind_first_lookup)
    loser, created = svc.create_event(session, title="Premiera modelu", kind="product_launch")
    assert not created and loser.id == winner.id
    session.commit()
    assert session.query(GeoEvent).count() == 1


# --- participants -----------------------------------------------------------------------------------------------


def test_participants_may_be_countries_organizations_and_persons(session):
    event = make(
        session,
        "Ogłoszenie pandemii",
        event_date="2020-03-11",
        kind="health",
        participants=[
            {"type": "organization", "ref": 1, "role": "actor"},
            {"type": "country", "ref": "brazylia", "role": "affected"},
            {"type": "person", "ref": "donald tusk", "role": "subject"},
            ("izrael", "affected"),
        ],
    )
    kinds = [(p["type"], p["role"]) for p in svc.event_to_dict(event)["participants"]]
    assert kinds == [("country", "affected"), ("country", "affected"), ("organization", "actor"), ("person", "subject")]
    organization = [p for p in svc.event_to_dict(event)["participants"] if p["type"] == "organization"][0]
    assert organization["organization"] == {"id": 1, "name": "WHO"}


def test_participant_references_are_checked(session):
    with pytest.raises(svc.GeopoliticsError) as unknown:
        svc.create_event(session, title="X", participants=[{"type": "organization", "ref": 999, "role": "actor"}])
    assert unknown.value.status == 404
    with pytest.raises(svc.GeopoliticsError) as ambiguous:
        svc.create_event(session, title="X", participants=[{"type": "organization", "ref": "Meta", "role": "actor"}])
    assert ambiguous.value.status == 409
    with pytest.raises(svc.GeopoliticsError):
        svc.create_event(session, title="X", participants=[{"type": "person", "ref": 1, "role": "location"}])
    with pytest.raises(svc.GeopoliticsError):
        svc.create_event(session, title="X", participants=[{"type": "planet", "ref": 1, "role": "actor"}])
    with pytest.raises(svc.GeopoliticsError):
        svc.create_event(session, title="X", participants=["brazylia"])


def test_participants_can_be_added_and_removed(session):
    event = make(session, "Szczyt")
    svc.add_participant(session, event, {"type": "country", "ref": "brazylia", "role": "host"})
    svc.add_participant(session, event, {"type": "organization", "ref": "who", "role": "organizer"})
    session.commit()
    assert len(svc.event_to_dict(event)["participants"]) == 2
    svc.remove_participant(session, event, "organization", 1, "organizer")
    session.commit()
    assert [p["type"] for p in svc.event_to_dict(event)["participants"]] == ["country"]
    with pytest.raises(svc.GeopoliticsError) as missing:
        svc.remove_participant(session, event, "organization", 1, "organizer")
    assert missing.value.status == 404


# --- editing, versions, aliases ----------------------------------------------------------------------------------


def test_editing_checks_the_version_and_keeps_the_old_title_as_a_name(session):
    event = make(session, "Wybory w Izraelu", participants=[("izrael", "location")])
    svc.update_event(session, event, expected_version=1, title="Wybory do Knesetu 2026", event_date="2026-11-03")
    session.commit()
    assert event.version == 2 and event.event_date.isoformat() == "2026-11-03"
    assert {a.alias for a in event.aliases} == {"Wybory w Izraelu", "Wybory do Knesetu 2026"}
    with pytest.raises(svc.GeopoliticsError) as stale:
        svc.update_event(session, event, expected_version=1, description="x")
    assert stale.value.status == 409
    svc.update_event(session, event, event_date="")
    assert event.event_date is None and event.date_precision == "unknown"
    with pytest.raises(svc.GeopoliticsError):
        svc.update_event(session, event, status="confirmed")


def test_aliases_are_unique_per_event_and_the_title_stays(session):
    event = make(session, "Wybory w Polsce")
    alias = svc.add_alias(session, event, "Polskie wybory")
    with pytest.raises(svc.GeopoliticsError) as duplicate:
        svc.add_alias(session, event, "polskie   WYBORY")
    assert duplicate.value.status == 409
    svc.remove_alias(session, event, alias.id)
    title_alias = next(a for a in event.aliases if a.alias == "Wybory w Polsce")
    with pytest.raises(svc.GeopoliticsError):
        svc.remove_alias(session, event, title_alias.id)


def test_the_same_alias_may_name_two_events(session):
    one = make(session, "Wybory parlamentarne w Polsce 2023", event_date="2023-10-15", aliases=["Wybory w Polsce"])
    two = make(session, "Wybory parlamentarne w Polsce 2027", event_date="2027-10-10", aliases=["Wybory w Polsce"])
    found = world.find_events_by_name(session, "wybory w polsce")
    assert {c["event"]["id"] for c in found} == {one.id, two.id} and all(c["reason"] == "alias" for c in found)


# --- listing ---------------------------------------------------------------------------------------------------


def test_listing_filters_and_orders_undated_events_last(session):
    make(session, "Wybory w Izraelu", event_date="2026-11-03", kind="election", participants=[("izrael", "location")])
    make(session, "Halving Bitcoina", kind="market")
    make(session, "Awaria CrowdStrike", event_date="2024-07-19", kind="outage")
    titles = lambda **kw: [e.title for e in svc.list_events(session, **kw)[0]]  # noqa: E731
    assert titles() == ["Wybory w Izraelu", "Awaria CrowdStrike", "Halving Bitcoina"]
    assert titles(with_countries=True) == ["Wybory w Izraelu"]
    assert titles(with_countries=False) == ["Awaria CrowdStrike", "Halving Bitcoina"]
    assert titles(undated=True) == ["Halving Bitcoina"]
    assert titles(kind="outage") == ["Awaria CrowdStrike"]
    assert titles(q="crowdstrike") == ["Awaria CrowdStrike"]
    assert titles(q="WYBORY w izraelu") == ["Wybory w Izraelu"]


def test_search_ignores_accents(session):
    make(session, "Wybory w Łodzi", event_date="2026-01-01")
    assert [e.title for e in svc.list_events(session, q="lodzi")[0]] == ["Wybory w Łodzi"]


# --- evidence: direct needs both countries, context is background -----------------------------------------------


def _pair(**kw):
    return dict(
        from_country="brazylia",
        to_country="stany-zjednoczone",
        axis="political",
        score=-1,
        valid_from="2026-03-10",
        **kw,
    )


def test_direct_evidence_must_name_both_countries(session):
    both = make(
        session,
        "Sankcje",
        event_date="2026-03-10",
        participants=[("brazylia", "target"), ("stany-zjednoczone", "actor")],
    )
    only_one = make(session, "Wybory w Brazylii", event_date="2026-03-01", participants=[("brazylia", "location")])
    none = make(session, "Awaria", event_date="2026-03-02")
    row = svc.create_assessment(session, event_ids=[both.id], **_pair())
    assert [(e.event_id, e.evidence_kind) for e in row.evidence] == [(both.id, "direct")]
    for event in (only_one, none):
        with pytest.raises(svc.GeopoliticsError) as exc:
            svc.create_assessment(session, event_ids=[event.id], **_pair())
        assert exc.value.status == 400 and "context" in exc.value.message


def test_context_events_need_a_rationale_and_never_justify_the_score(session):
    both = make(
        session,
        "Sankcje",
        event_date="2026-03-10",
        participants=[("brazylia", "target"), ("stany-zjednoczone", "actor")],
    )
    context = make(session, "Wybory w Brazylii", event_date="2026-03-01", participants=[("brazylia", "location")])
    with pytest.raises(svc.GeopoliticsError):
        svc.create_assessment(session, event_ids=[both.id], context_event_ids=[context.id], **_pair())
    row = svc.create_assessment(
        session,
        event_ids=[both.id],
        context_event_ids=[context.id, both.id],
        rationale="Nowy rząd, nowa polityka wobec USA.",
        **_pair(),
    )
    session.commit()
    assert sorted((e.event_id, e.evidence_kind) for e in row.evidence) == sorted(
        [(both.id, "direct"), (context.id, "context")]
    )
    dumped = svc.assessment_to_dict(row, with_evidence=True)["evidence"]
    assert {(e["event"]["id"], e["kind"]) for e in dumped} == {(both.id, "direct"), (context.id, "context")}


def test_only_direct_evidence_counts_for_confidence(session):
    both = make(
        session,
        "Sankcje",
        event_date="2026-03-10",
        participants=[("brazylia", "target"), ("stany-zjednoczone", "actor")],
    )
    context = make(session, "Wybory w Brazylii", event_date="2026-03-01", participants=[("brazylia", "location")])
    svc.add_participant  # noqa: B018 - keeps the import used when the test is skipped
    for event, document in ((both, 1), (context, 2)):
        svc._add_source(session, event, {"document_id": document, "quote": f"cytat {document}"})
    row = svc.create_assessment(
        session, event_ids=[both.id], context_event_ids=[context.id], rationale="tło", confidence=0.95, **_pair()
    )
    assert float(row.confidence) == svc.SINGLE_EVENT_CONFIDENCE_CAP  # the context event's document is not independent


def test_a_repeated_proposal_adds_direct_and_context_evidence(session):
    both = make(
        session,
        "Sankcje",
        event_date="2026-03-10",
        participants=[("brazylia", "target"), ("stany-zjednoczone", "actor")],
    )
    more = make(
        session, "Cła", event_date="2026-03-10", participants=[("brazylia", "target"), ("stany-zjednoczone", "actor")]
    )
    context = make(session, "Wybory w Brazylii", event_date="2026-03-01", participants=[("brazylia", "location")])
    first, created = svc.propose_assessment(session, event_ids=[both.id], **_pair())
    again, created_again = svc.propose_assessment(
        session, event_ids=[more.id], context_event_ids=[context.id], **_pair()
    )
    assert created and not created_again and again.id == first.id
    assert sorted(e.evidence_kind for e in again.evidence) == ["context", "direct", "direct"]
    with pytest.raises(svc.GeopoliticsError):
        svc.propose_assessment(session, event_ids=[context.id], **_pair())


def test_a_country_that_confirmed_direct_evidence_relies_on_cannot_be_removed(session):
    both = make(
        session,
        "Sankcje",
        event_date="2026-03-10",
        participants=[("brazylia", "target"), ("stany-zjednoczone", "actor")],
    )
    row = svc.create_assessment(session, event_ids=[both.id], status="confirmed", **_pair())
    session.commit()
    brazil = session.query(Country).filter_by(slug="brazylia").one()
    with pytest.raises(svc.GeopoliticsError) as exc:
        svc.remove_participant(session, both, "country", brazil.id, "target")
    assert exc.value.status == 409 and row.status == "confirmed"


# --- named-event mentions ---------------------------------------------------------------------------------------


@pytest.fixture
def mentions(session):
    add_event_mention(session, 1, 1, "Wybory w Izraelu", "Przedterminowe wybory.", 3)
    add_event_mention(session, 2, 2, "wybory w izraelu", None, 2)
    add_event_mention(session, 3, 3, "Galanbard 2026", None, 1)
    add_event_mention(session, 4, 4, "Wybory w Polsce", None, 1)
    session.commit()
    return session


def test_mentions_are_grouped_by_normalized_name_across_documents(mentions):
    groups, total = world.unlinked_mentions(mentions)
    assert total == 3
    israel = next(g for g in groups if g["name_key"] == "wybory w izraelu")
    assert (
        israel["mentions"] == 5 and israel["document_count"] == 2 and israel["description"] == "Przedterminowe wybory."
    )
    assert [g["name_key"] for g in groups] == ["galanbard 2026", "wybory w izraelu", "wybory w polsce"]
    assert [g["name_key"] for g in world.unlinked_mentions(mentions, q="IZRAELU")[0]] == ["wybory w izraelu"]
    assert world.unlinked_mentions(mentions, limit=1, offset=1)[0][0]["name_key"] == "wybory w izraelu"


def test_a_known_alias_is_suggested_but_never_linked_on_its_own(mentions):
    event = make(mentions, "Wybory do Knesetu 2026", aliases=["Wybory w Izraelu"], kind="election")
    israel = next(g for g in world.unlinked_mentions(mentions)[0] if g["name_key"] == "wybory w izraelu")
    assert [(s["event"]["id"], s["reason"]) for s in israel["suggestions"]] == [(event.id, "alias")]
    assert mentions.query(GeoEventMentionLink).count() == 0


def test_linking_a_name_links_every_document_and_teaches_the_alias(mentions):
    event = make(mentions, "Wybory do Knesetu 2026", kind="election")
    assert world.link_mentions(mentions, "Wybory w Izraelu", event.id, user_id=7) == 2
    mentions.commit()
    assert "wybory w izraelu" in {a.name_key for a in event.aliases}
    assert "wybory w izraelu" not in [g["name_key"] for g in world.unlinked_mentions(mentions)[0]]
    assert world.link_mentions(mentions, "Wybory w Izraelu", event.id) == 2  # idempotent
    assert mentions.query(GeoEventMentionLink).count() == 2
    index, _ = world.world_events_index(mentions)
    row = next(item for item in index if item["id"] == event.id)
    assert row["document_count"] == 2 and row["mention_names"] == ["Wybory w Izraelu", "wybory w izraelu"]
    assert {d["id"]: d["via"] for d in row["documents"]} == {1: "mention", 2: "mention"}


def test_linking_can_be_narrowed_to_some_documents_and_undone(mentions):
    event = make(mentions, "Wybory do Knesetu 2026")
    assert world.link_mentions(mentions, "Wybory w Izraelu", event.id, document_ids=[1]) == 1
    groups = world.unlinked_mentions(mentions)[0]
    israel = next(g for g in groups if g["name_key"] == "wybory w izraelu")
    assert [d["id"] for d in israel["documents"]] == [2]
    assert world.unlink_mentions(mentions, "Wybory w Izraelu", event.id) == 1
    assert (
        next(g for g in world.unlinked_mentions(mentions)[0] if g["name_key"] == "wybory w izraelu")["document_count"]
        == 2
    )
    with pytest.raises(svc.GeopoliticsError) as exc:
        world.unlink_mentions(mentions, "Wybory w Izraelu", event.id)
    assert exc.value.status == 404


def test_a_rejected_suggestion_is_not_made_again_but_others_are(mentions):
    wrong = make(mentions, "Wybory w Izraelu 2022", aliases=["Wybory w Izraelu"], event_date="2022-11-01")
    right = make(mentions, "Wybory w Izraelu 2026", aliases=["Wybory w Izraelu"], event_date="2026-11-03")
    world.reject_suggestion(mentions, "Wybory w Izraelu", wrong.id)
    mentions.commit()
    israel = next(g for g in world.unlinked_mentions(mentions)[0] if g["name_key"] == "wybory w izraelu")
    assert [s["event"]["id"] for s in israel["suggestions"]] == [right.id]
    assert israel["document_count"] == 2  # a rejection links nothing
    world.link_mentions(mentions, "Wybory w Izraelu", right.id)
    world.reject_suggestion(mentions, "Wybory w Izraelu", right.id)  # a confirmed link survives a later rejection
    assert mentions.query(GeoEventMentionLink).filter_by(event_id=right.id, status="confirmed").count() == 2


def test_the_reader_can_create_an_event_from_a_mention(mentions):
    event, created, linked = world.create_event_from_mention(mentions, "wybory w izraelu", kind="election", user_id=3)
    mentions.commit()
    assert created and linked == 2 and event.status == "confirmed" and event.kind == "election"
    assert event.title == "Wybory w Izraelu" and event.event_date is None
    again, created_again, _ = world.create_event_from_mention(mentions, "Wybory w Izraelu", kind="election")
    assert not created_again and again.id == event.id
    with pytest.raises(svc.GeopoliticsError) as exc:
        world.create_event_from_mention(mentions, "Nie ma takiego")
    assert exc.value.status == 404


def test_a_trigram_search_is_only_attempted_on_postgresql(mentions):
    make(mentions, "Wybory w Izraelu 2026", event_date="2026-11-03")
    assert world.find_events_by_name(mentions, "Wybory w Izraelu 2026")[0]["reason"] == "alias"
    assert world.find_events_by_name(mentions, "wybory izrael")[0:1] == []  # SQLite: no similarity()


# --- the timeline of one document ---------------------------------------------------------------------------------


def test_a_timeline_entry_becomes_an_event_with_its_source(session):
    add_document_event(session, 10, 1, "Bank centralny podniósł stopy o 25 punktów bazowych.", "2026-03-10")
    add_document_event(session, 11, 2, "Upadek imperium.", "0476-09-04", precision="era")
    session.commit()
    event, created = world.promote_document_event(session, 10, kind="market", user_id=2)
    session.commit()
    assert created and event.event_date.isoformat() == "2026-03-10" and event.kind == "market"
    assert event.status == "proposed" and event.title.startswith("Bank centralny")
    assert (event.sources[0].document_id, event.sources[0].document_event_id) == (1, 10)
    vague, _ = world.promote_document_event(session, 11)
    assert vague.event_date is None and vague.date_precision == "unknown" and "Data w tekście" in vague.description


def test_a_timeline_entry_can_back_an_existing_event_from_another_document(session):
    event = make(session, "Podwyżka stóp", event_date="2026-03-10")
    add_document_event(session, 10, 2, "Bank podniósł stopy.", "2026-03-10")
    session.commit()
    same, created = world.promote_document_event(session, 10, event_id=event.id)
    session.commit()
    assert not created and same.id == event.id and [s.document_id for s in same.sources] == [2]
    with pytest.raises(svc.GeopoliticsError) as exc:
        world.promote_document_event(session, 999)
    assert exc.value.status == 404
    with pytest.raises(svc.GeopoliticsError):
        svc._add_source(session, event, {"document_id": 1, "quote": "x", "document_event_id": 10})  # belongs to doc 2


# --- HTTP -----------------------------------------------------------------------------------------------------------


def test_dictionaries_over_http(client):
    kinds = client.get("/geo_event_kinds").get_json()["kinds"]
    assert {"code": "election", "label": "Wybory"} in kinds and len(kinds) == 16
    assert {"code": "host", "label": "gospodarz"} in client.get("/geo_event_roles").get_json()["roles"]


def test_creating_and_editing_an_event_over_http(client):
    body = {
        "title": "Ogłoszenie pandemii",
        "kind": "health",
        "event_date": "2020-03-11",
        "aliases": ["Pandemia COVID-19"],
        "participants": [{"type": "organization", "ref": 1, "role": "actor"}],
    }
    created = client.post("/geo_events", json=body)
    assert created.status_code == 201
    event = created.get_json()["event"]
    assert event["participants"][0]["organization"]["name"] == "WHO" and len(event["aliases"]) == 2
    assert client.post("/geo_events", json=body).status_code == 200  # same report

    edited = client.patch(
        f"/geo_events/{event['id']}", json={"description": "WHO ogłosiła pandemię.", "expected_version": 1}
    )
    assert edited.status_code == 200 and edited.get_json()["event"]["version"] == 2
    stale = client.patch(f"/geo_events/{event['id']}", json={"description": "x", "expected_version": 1})
    assert stale.status_code == 409
    assert client.patch(f"/geo_events/{event['id']}", json={}).status_code == 400
    assert (
        client.patch(f"/geo_events/{event['id']}", json={"status": "confirmed"}).get_json()["event"]["status"]
        == "confirmed"
    )
    assert client.get(f"/geo_events/{event['id']}").get_json()["event"]["title"] == "Ogłoszenie pandemii"
    assert client.get("/geo_events/9999").status_code == 404
    assert client.post("/geo_events", json={"title": "x", "participants": "WHO"}).status_code == 400
    assert client.post("/geo_events", json={"title": "x", "aliases": [1]}).status_code == 400


def test_aliases_and_participants_over_http(client):
    event = client.post("/geo_events", json={"title": "Szczyt"}).get_json()["event"]
    url = f"/geo_events/{event['id']}"
    added = client.post(f"{url}/aliases", json={"alias": "Szczyt G20"})
    assert added.status_code == 201
    alias_id = [a["id"] for a in added.get_json()["event"]["aliases"] if a["alias"] == "Szczyt G20"][0]
    assert client.post(f"{url}/aliases", json={"alias": "szczyt g20"}).status_code == 409
    assert client.delete(f"{url}/aliases/{alias_id}").status_code == 200
    assert client.delete(f"{url}/aliases/{alias_id}").status_code == 404

    joined = client.post(f"{url}/participants", json={"type": "country", "ref": "brazylia", "role": "host"})
    assert joined.status_code == 201 and joined.get_json()["event"]["participants"][0]["role"] == "host"
    assert client.post(f"{url}/participants", json={"type": "person", "ref": 1, "role": "location"}).status_code == 400
    brazil_id = joined.get_json()["event"]["participants"][0]["country"]["id"]
    assert (
        client.delete(f"{url}/participants", json={"type": "country", "id": brazil_id, "role": "host"}).status_code
        == 200
    )
    assert (
        client.delete(f"{url}/participants", json={"type": "country", "id": brazil_id, "role": "host"}).status_code
        == 404
    )
    assert client.delete(f"{url}/participants", json={"type": "country", "role": "host"}).status_code == 400


def test_filters_over_http(client):
    client.post("/geo_events", json={"title": "Halving Bitcoina", "kind": "market"})
    client.post(
        "/geo_events",
        json={
            "title": "Wybory w Izraelu",
            "kind": "election",
            "event_date": "2026-11-03",
            "participants": [{"type": "country", "ref": "izrael", "role": "location"}],
        },
    )
    titles = lambda query: [e["title"] for e in client.get(f"/geo_events?{query}").get_json()["events"]]  # noqa: E731
    assert titles("with_countries=1") == ["Wybory w Izraelu"] and titles("undated=1") == ["Halving Bitcoina"]
    assert titles("kind=market") == ["Halving Bitcoina"] and titles("q=halving") == ["Halving Bitcoina"]
    assert client.get("/geo_events?kind=nonsense").status_code == 400


def test_world_events_index_filters_by_country_and_status(client):
    client.post("/geo_events", json={"title": "Halving Bitcoina", "kind": "market"})
    client.post(
        "/geo_events",
        json={
            "title": "Wybory w Izraelu",
            "kind": "election",
            "participants": [{"type": "country", "ref": "izrael", "role": "location"}],
        },
    )
    titles = lambda query: [e["title"] for e in client.get(f"/world_events?{query}").get_json()["events"]]  # noqa: E731
    assert titles("country=izrael") == ["Wybory w Izraelu"]
    assert client.get("/world_events?country=nie-ma-takiego-kraju").status_code in (400, 404)
    assert sorted(titles("status=proposed") + titles("status=confirmed")) == sorted(titles(""))
    assert client.get("/world_events?status=nonsense").status_code == 400


def test_the_mention_queue_and_decisions_over_http(client, session):
    add_event_mention(session, 1, 1, "Wybory w Izraelu", None, 2)
    add_event_mention(session, 2, 2, "Wybory w Izraelu", None, 1)
    session.commit()
    queue = client.get("/world_events/unlinked").get_json()
    assert queue["total"] == 1 and queue["mentions"][0]["document_count"] == 2

    made = client.post("/world_events/from_mention", json={"name": "Wybory w Izraelu", "kind": "election"})
    assert made.status_code == 201 and made.get_json()["linked_documents"] == 2
    event_id = made.get_json()["event"]["id"]
    assert client.get("/world_events/unlinked").get_json()["total"] == 0
    index = client.get("/world_events?kind=election").get_json()
    assert index["total"] == 1 and index["events"][0]["document_count"] == 2 and index["events"][0]["id"] == event_id

    assert (
        client.post(
            "/world_events/mentions/unlink", json={"name": "Wybory w Izraelu", "event_id": event_id, "document_id": 1}
        ).get_json()["removed"]
        == 1
    )
    assert client.get("/world_events/unlinked").get_json()["total"] == 1
    relinked = client.post("/world_events/mentions/link", json={"name": "Wybory w Izraelu", "event_id": event_id})
    assert relinked.get_json()["linked_documents"] == 2
    assert (
        client.post(
            "/world_events/mentions/reject", json={"name": "Wybory w Izraelu", "event_id": event_id}
        ).status_code
        == 200
    )
    candidates = client.get("/world_events/candidates?name=wybory w izraelu").get_json()["candidates"]
    assert candidates[0]["event"]["id"] == event_id


def test_decision_endpoints_validate_their_input(client):
    assert client.post("/world_events/mentions/link", json={"name": "", "event_id": 1}).status_code == 400
    assert client.post("/world_events/mentions/link", json={"name": "x", "event_id": "1"}).status_code == 400
    assert client.post("/world_events/mentions/link", json={"name": "x", "event_id": 999}).status_code == 404
    assert (
        client.post("/world_events/mentions/link", json={"name": "x", "event_id": 1, "document_ids": "all"}).status_code
        == 400
    )
    assert client.post("/world_events/from_mention", json={}).status_code == 400
    assert client.post("/world_events/from_mention", json={"name": "Nie ma takiego"}).status_code == 404
    assert client.get("/world_events/candidates").status_code == 400
    assert client.get("/world_events?status=weird").status_code == 400


def test_a_timeline_entry_is_promoted_over_http(client, session):
    add_document_event(session, 10, 1, "Bank podniósł stopy.", "2026-03-01", precision="month")
    session.commit()
    promoted = client.post("/document_events/10/to_world_event", json={"kind": "market"})
    assert promoted.status_code == 201
    body = promoted.get_json()["event"]
    assert body["date_precision"] == "month" and body["sources"][0]["document_id"] == 1
    assert client.post("/document_events/999/to_world_event", json={}).status_code == 404


def test_context_evidence_over_http(client, session):
    both = client.post(
        "/geo_events",
        json={
            "title": "Sankcje",
            "event_date": "2026-03-10",
            "participants": [
                {"type": "country", "ref": "brazylia", "role": "target"},
                {"type": "country", "ref": "stany-zjednoczone", "role": "actor"},
            ],
        },
    ).get_json()["event"]
    context = client.post(
        "/geo_events",
        json={
            "title": "Wybory w Brazylii",
            "event_date": "2026-03-01",
            "participants": [{"type": "country", "ref": "brazylia", "role": "location"}],
        },
    ).get_json()["event"]
    base = {"from": "brazylia", "to": "stany-zjednoczone", "axis": "political", "score": -1, "valid_from": "2026-03-10"}
    refused = client.post("/country_relations", json={**base, "event_ids": [context["id"]]})
    assert refused.status_code == 400 and "context" in refused.get_json()["message"]
    ok = client.post(
        "/country_relations",
        json={**base, "event_ids": [both["id"]], "context_event_ids": [context["id"]], "rationale": "Nowy rząd."},
    )
    assert ok.status_code == 201
    assert sorted(e["kind"] for e in ok.get_json()["assessment"]["evidence"]) == ["context", "direct"]
    assert session.query(CountryRelationEvidence).count() == 2 and session.query(CountryRelationAssessment).count() == 1


def test_promoted_entries_are_reported_back_to_the_timeline_panel(client, session):
    from library import chunk_review_routes

    add_document_event(session, 20, 1, "Wstrzymano dostawy gazu.", "2022-08-01", precision="month")
    add_document_event(session, 21, 1, "Inny wpis.", "2023-01-01", precision="year")
    session.commit()
    created = client.post("/document_events/20/to_world_event", json={"title": "Nord Stream 1 wstrzymany"})
    assert created.status_code == 201

    promoted = chunk_review_routes._promoted_world_events(session, [20, 21])

    assert promoted == {20: [{"id": created.get_json()["event"]["id"], "title": "Nord Stream 1 wstrzymany"}]}
    assert chunk_review_routes._promoted_world_events(session, []) == {}
