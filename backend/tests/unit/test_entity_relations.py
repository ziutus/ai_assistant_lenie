"""Offline contracts for entity relations, extraction, Wikidata and graph expansion."""

import datetime
import json
from types import SimpleNamespace

import flask
import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from library import entity_relations_service as svc
from library import entity_relation_routes as routes
from library.db.engine import Base
from library.db.models import (
    Document, DocumentEntity, DocumentOrganization, DocumentPerson, EntityRelation, EntityRelationEvidence,
    Organization, OrganizationAlias, OrganizationCountry, Person, PersonAlias, PersonTerritory,
)
from tests.unit.geo_sqlite_support import make_engine


@pytest.fixture
def session():
    engine = make_engine()
    Base.metadata.create_all(engine, tables=[m.__table__ for m in
                             (EntityRelation, EntityRelationEvidence, OrganizationCountry, PersonTerritory)])
    with engine.begin() as conn:
        for model in (Document, DocumentEntity, DocumentOrganization, DocumentPerson, Person, PersonAlias,
                      Organization, OrganizationAlias):
            columns = ["id INTEGER PRIMARY KEY"] + [c.name for c in model.__table__.columns if c.name != "id"]
            conn.execute(text(f"CREATE TABLE {model.__tablename__} ({', '.join(columns)})"))
        conn.execute(text("INSERT INTO persons (id, canonical_name, wikidata_qid) VALUES "
                          "(1, 'Ada Brzask', 'Q1'), (2, 'Iwo Dąb', 'Q2'), (3, 'Iwo Dąb', NULL)"))
        conn.execute(text("INSERT INTO organizations (id, canonical_name) VALUES (1, 'Ministerstwo'), (2, 'Gabinet')"))
        conn.execute(text("INSERT INTO documents (id, title, document_type, text) VALUES "
                          "(10, 'Artykuł', 'webpage', 'Ada Brzask pracuje dla Ministerstwo w Polsce.')"))
        conn.execute(text("INSERT INTO document_persons (id, document_id, person_id, raw_mention) "
                          "VALUES (1, 10, 1, 'Ada Brzask')"))
        conn.execute(text("INSERT INTO document_organizations (id, document_id, organization_id) VALUES (1, 10, 1)"))
    with Session(engine) as db:
        yield db


P1, P2, P3 = ({"type": "person", "id": i} for i in (1, 2, 3))
O1, O2 = ({"type": "organization", "id": i} for i in (1, 2))
COUNTRY = {"type": "country", "slug": "polska"}


def test_symmetric_periods_and_evidence(session):
    evidence = {"document_id": 10, "quote": "Ada i Iwo", "claim": "fakt"}
    row, created, added = svc.upsert_relation(session, P2, "malzonek", P1, evidence=evidence,
                                             valid_from="2000-01-01", valid_to="2005-01-01")
    assert created and added and row.subject_person_id == 1
    other, created, added = svc.upsert_relation(session, P1, "malzonek", P2, evidence=evidence)
    assert row is other and not created and not added
    _, created, _ = svc.upsert_relation(session, P1, "malzonek", P2, valid_from="2010-01-01")
    assert created
    assert svc.relations_for_person(session, 2)[0]["direction"] == "incoming"
    assert svc.relations_for_person(session, 2)[0]["evidence"][0]["document_title"] == "Artykuł"


def test_decisions_not_overwritten_by_proposals(session):
    row, _, _ = svc.upsert_relation(session, P1, "funkcja_publiczna", O1, title="minister")
    svc.decide_relation(session, row, "confirmed")
    svc.upsert_relation(session, P1, "funkcja_publiczna", O1, title="prezes", valid_from="2020-01-01")
    assert row.title == "minister" and row.valid_from is None
    svc.decide_relation(session, row, "rejected")
    svc.upsert_relation(session, P1, "funkcja_publiczna", O1, evidence={"quote": "nowy cytat"})
    assert row.status == "rejected" and not svc.relations_for_person(session, 1)
    assert len(svc.relations_for_person(session, 1, True)) == 1


def test_projection_ownership_and_edit(session):
    row, _ = svc.manual_create(session, P1, "obywatel", COUNTRY, valid_from="2000-01-01")
    truth = session.get(PersonTerritory, row.projected_row_id)
    assert truth.valid_from == datetime.date(2000, 1, 1)
    svc.edit_relation(session, row, valid_to="2010-12-31")
    assert truth.valid_to == datetime.date(2010, 12, 31)
    assert len(svc.relations_for_person(session, 1)) == 1
    svc.decide_relation(session, row, "rejected")
    assert session.scalar(select(PersonTerritory)) is None
    prior = OrganizationCountry(organization_id=1, country_slug="polska", relation="based_in")
    session.add(prior)
    session.flush()
    row, _ = svc.manual_create(session, O1, "siedziba", COUNTRY)
    assert row.projected_row_id is None
    svc.delete_relation(session, row)
    assert session.get(OrganizationCountry, prior.id) is prior
    assert svc.relations_for_organization(session, 1)[0]["editable"] is False


def test_projection_survives_another_confirmed_term(session):
    first, _ = svc.manual_create(session, P1, "funkcja_publiczna", COUNTRY,
                                 valid_from="2000-01-01", valid_to="2005-01-01")
    second, _ = svc.manual_create(session, P1, "funkcja_publiczna", COUNTRY, valid_from="2010-01-01")
    identifier = first.projected_row_id
    svc.delete_relation(session, first)
    assert second.projected_row_id == identifier
    svc.delete_relation(session, second)
    assert session.get(PersonTerritory, identifier) is None


def test_merge_moves_evidence_keeps_confirmed_drops_self(session):
    target, _, _ = svc.upsert_relation(session, P2, "pracownik", O1, evidence={"quote": "drugi"})
    source, _, _ = svc.upsert_relation(session, P1, "pracownik", O1, evidence={"quote": "pierwszy"})
    svc.decide_relation(session, source, "confirmed")
    svc.upsert_relation(session, P1, "rodzic", P2)
    svc.absorb_relations(session, "person", 1, 2)
    rows = session.scalars(select(EntityRelation)).all()
    assert rows == [target] and target.status == "confirmed"
    assert {e.quote for e in target.evidence} == {"pierwszy", "drugi"}
    assert svc.has_relations(session, "person", 2)
    assert not svc.has_relations(session, "person", 1)


def test_organization_merge_moves_owned_projection(session):
    row, _ = svc.manual_create(session, O1, "siedziba", COUNTRY)
    svc.absorb_relations(session, "organization", 1, 2)
    assert row.subject_organization_id == 2
    truth = session.scalars(select(OrganizationCountry)).all()
    assert len(truth) == 1 and truth[0].organization_id == 2


@pytest.mark.parametrize("left,role,right,fields", [
    (P1, "rodzic", P1, {}), (O1, "rodzic", P1, {}), (P1, "unknown", O1, {}),
    (P1, "obywatel", {"type": "country", "slug": "unknown"}, {}),
    (P1, "pracownik", O1, {"valid_from": "2025-01-01", "valid_to": "2024-01-01"}),
])
def test_validation(session, left, role, right, fields):
    with pytest.raises(svc.RelationError):
        svc.upsert_relation(session, left, role, right, **fields)


def test_graph_chain_and_period(session):
    from library.entity_relations_graph import extend_relationship_graph
    relation, _, _ = svc.upsert_relation(session, P1, "funkcja_publiczna", O2, title="minister",
                                         valid_from="2020-01-01", valid_to="2021-12-31")
    svc.manual_create(session, O2, "siedziba", COUNTRY)
    svc.upsert_relation(session, P1, "rodzic", P2)
    session.execute(text("INSERT INTO organizations (id, canonical_name) VALUES (3, 'Poza dokumentem')"))
    svc.upsert_relation(session, P2, "pracownik", {"type": "organization", "id": 3})  # no second person hop
    nodes, edges = [], []
    extend_relationship_graph(session, SimpleNamespace(id=10, published_on=datetime.date(2023, 1, 1)), nodes, edges)
    assert {n["id"] for n in nodes} == {"person:1", "person:2", "organization:2", "country:polska"}
    edge = next(e for e in edges if e.get("relation_id") == relation.id)
    assert edge["outside_period"] and edge["type"] == "minister (2020–2021)"
    assert ("organization:2", "country:polska") in {(e["source"], e["target"]) for e in edges}


def test_detection_closed_names_and_known_payload(session):
    from library.entity_relations_detect import detect_for_document
    svc.manual_create(session, P1, "pracownik", O1)
    calls = []

    def ask(query, model, **kwargs):
        payload = json.loads(query)
        calls.append(payload)
        if "proposals" in payload:
            return json.dumps({"verdicts": []})
        return json.dumps({"relations": [
            dict(subject="Ada Brzask", subject_type="osoba", relation="pracownik", object="Ministerstwo",
                 object_type="organizacja", claim="fakt", quote="Ada Brzask pracuje dla Ministerstwo"),
            dict(subject="Nieznany", subject_type="osoba", relation="pracownik", object="Ministerstwo",
                 object_type="organizacja", claim="fakt", quote="Ada Brzask pracuje dla Ministerstwo"),
        ]})
    result = detect_for_document(session, 10, model="fake", ask=ask)
    assert result["created"] == 0 and result["evidence_added"] == 1
    assert result["unresolved"][0]["failed_ends"] == ["subject"]
    assert calls[0]["known_relations"][0]["status"] == "confirmed"
    assert result["usage"]["llm_calls"] == 2


def claim(qid, **extra):
    return {"mainsnak": {"datavalue": {"value": {"id": qid}}}, **extra}


def test_wikidata_positions_family_and_dates(session):
    from library.wikidata_relations import propose_for_person
    date = {"datavalue": {"value": {"time": "+2020-00-00T00:00:00Z", "precision": 9}}}
    data = {
        "Q1": {"claims": {"P39": [claim("Q10", qualifiers={"P580": [date], "P582": [date]})],
                          "P22": [claim("Q2")], "P102": [claim("Q11")]}},
        "Q10": {"labels": {"pl": {"value": "minister"}}, "claims": {"P2389": [claim("Q11")], "P17": [claim("Q36")]}},
        "Q11": {"labels": {"pl": {"value": "Ministerstwo"}}},
        "Q36": {"labels": {"pl": {"value": "Polska"}}},
        "Q2": {"labels": {"pl": {"value": "Iwo Dąb"}}},
    }
    result = propose_for_person(session, 1, fetch=lambda ids: {i: data[i] for i in ids})
    assert result["created"] == 4 and not result["unresolved"]
    parent = session.scalar(select(EntityRelation).where(EntityRelation.relation == "rodzic"))
    assert parent.subject_person_id == 2 and parent.object_person_id == 1
    office = session.scalar(select(EntityRelation).where(EntityRelation.relation == "funkcja_publiczna"))
    assert office.valid_from == datetime.date(2020, 1, 1) and office.valid_to == datetime.date(2020, 12, 31)
    assert office.status == "proposed" and not session.scalar(select(OrganizationCountry))


def test_wikidata_failure_writes_nothing(session):
    from library.wikidata_relations import WikidataError, propose_for_person
    calls = []

    def fetch(ids):
        calls.append(ids)
        if len(calls) == 1:
            return {"Q1": {"claims": {"P26": [claim("Q2")]}}}
        raise WikidataError("secret provider text")
    with pytest.raises(WikidataError):
        propose_for_person(session, 1, fetch=fetch)
    assert session.scalar(select(EntityRelation)) is None


def test_wikidata_namesakes_unresolved(session):
    from library.wikidata_relations import resolve_target
    assert resolve_target(session, "person", "Q999", {"Q999": {"labels": {"pl": {"value": "Iwo Dąb"}}}}) is None


@pytest.fixture
def api(session, monkeypatch):
    app = flask.Flask(__name__)
    app.register_blueprint(routes.bp)
    monkeypatch.setattr(routes, "get_scoped_session", lambda: session)
    return app.test_client()


def test_routes_crud_and_validation(api):
    data = dict(subject=P1, relation="pracownik", object=O1, title="specjalista")
    response = api.post("/entity_relations", json=data)
    assert response.status_code == 201
    identifier = response.json["relation"]["id"]
    assert response.json["relation"]["status"] == "confirmed"
    assert api.get("/persons/1/relations").json["relations"][0]["other"]["id"] == 1
    assert len(api.get("/document/10/relations").json["relations"]) == 1
    assert api.patch(f"/entity_relations/{identifier}", json={"status": "rejected"}).status_code == 200
    assert api.get("/organizations/1/relations").json["relations"] == []
    assert len(api.get("/organizations/1/relations?include_rejected=1").json["relations"]) == 1
    assert api.delete(f"/entity_relations/{identifier}").status_code == 200
    assert api.delete(f"/entity_relations/{identifier}").status_code == 404
    assert api.post("/entity_relations", json=[]).status_code == 400
    assert api.post("/entity_relations", json=dict(data, relation="secret")).json["message"] == "Invalid relation data"
    assert api.get("/entity_relations/vocabulary").status_code == 200


def test_busy_route(api):
    from library.document_busy import claim_document
    with claim_document(10, "test"):
        assert api.post("/document/10/relations/detect", json={}).status_code == 409


def test_person_orphan_guard_and_merge_integration(session):
    from library.person_registry import _delete_person_if_orphaned, merge_review_link
    svc.upsert_relation(session, P2, "pracownik", O1)
    assert _delete_person_if_orphaned(session, 2) is False
    source, _, _ = svc.upsert_relation(session, P1, "pracownik", O2, evidence={"quote": "zachowaj"})
    link = session.get(DocumentPerson, 1)
    result = merge_review_link(session, link, session.get(Person, 2))
    assert result["person_deleted"]
    assert source.subject_person_id == 2 and source.evidence[0].quote == "zachowaj"


def test_organization_delete_refuses_relations(session):
    from library.organization_registry import OrganizationInUseError, delete_unused_organization
    svc.upsert_relation(session, P1, "pracownik", O2)
    with pytest.raises(OrganizationInUseError):
        delete_unused_organization(session, session.get(Organization, 2))


def test_cross_type_symmetric_is_canonical(session):
    first, _, _ = svc.upsert_relation(session, O1, "partner", P1)
    second, created, _ = svc.upsert_relation(session, P1, "partner", O1)
    assert first is second and not created and first.subject_person_id == 1


def test_failed_chunk_does_not_abort_and_chunks_are_capped(session):
    from library.entity_relations_detect import detect_for_document
    document = session.get(Document, 10)
    document.text = "a" * 6000 + "b" * 6000 * 11

    def ask(query, model, **kwargs):
        if json.loads(query)["text"].startswith("a"):
            raise RuntimeError("provider secret")
        return '{"relations": []}'
    result = detect_for_document(session, 10, model="fake", ask=ask)
    assert result["chunks"] == 10 and result["skipped_chunks"] == 2 and result["failed_calls"] == 1
    assert result["created"] == 0


def test_pipeline_kinship_country_and_known_filter():
    from library.relation_extraction import extract_relations, PROMPT_VERSION
    payloads = []
    fragment = "Iwo Dąb jest zięciem Ady Brzask. Ada Brzask jest obywatelką Polski."

    def ask(query, model, **kwargs):
        payloads.append(json.loads(query))
        return json.dumps({"relations": [
            dict(subject="Iwo Dąb", subject_type="osoba", relation="ziec_synowa", object="Ada Brzask",
                 object_type="osoba", title="zięć", claim="fakt", quote="Iwo Dąb jest zięciem Ady Brzask."),
            dict(subject="Ada Brzask", subject_type="osoba", relation="obywatel", object="Polska",
                 object_type="kraj", claim="fakt", quote="Ada Brzask jest obywatelką Polski."),
        ]})
    result = extract_relations(fragment, [], "fake", ask=ask, verify=False, known_relations=[
        dict(subject="Ada Brzask", object="Polska", relation="obywatel", title=None, status="rejected"),
        dict(subject="Nieobecny", object="Polska", relation="obywatel", title=None, status="confirmed"),
    ])
    assert len(result["relations"]) == 2 and PROMPT_VERSION == "relations-pl-v3"
    assert payloads[0]["known_relations"] == [
        dict(subject="Ada Brzask", object="Polska", relation="obywatel", title=None, status="rejected")]
    assert result["relations"][0]["title"] == "zięć"


def test_model_routes(api, monkeypatch):
    from library import app_settings, llm_model_registry, entity_relations_detect
    saved = {}
    monkeypatch.setattr(app_settings, "set_setting", lambda session, key, value: saved.update({key: value}))
    monkeypatch.setattr(app_settings, "get_setting", lambda session, key: saved.get(key))
    monkeypatch.setattr(llm_model_registry, "is_selectable", lambda model, task: model == "fake")
    monkeypatch.setattr(llm_model_registry, "selectable_models", lambda task: [{"id": "fake", "available": True}])
    assert api.get("/relation_extraction/model").json["default_model"] == "fake"
    assert api.put("/relation_extraction/model", json={"model": "fake"}).json["saved"] is True
    assert saved[entity_relations_detect.SETTING_KEY] == "fake"
    assert api.put("/relation_extraction/model", json={"model": None}).json["saved"] is False
    assert api.put("/relation_extraction/model", json={"model": "unknown"}).status_code == 400


def test_detection_and_wikidata_routes(api, monkeypatch):
    from library import entity_relations_detect, wikidata_relations
    monkeypatch.setattr(entity_relations_detect, "detect_for_document", lambda *a, **k: {"created": 0})
    monkeypatch.setattr(wikidata_relations, "propose_for_person", lambda *a, **k: {"created": 1})
    assert api.post("/document/10/relations/detect", json={}).json["created"] == 0
    assert api.post("/persons/1/relations/wikidata").json["created"] == 1

    def fail(*args, **kwargs):
        raise wikidata_relations.WikidataError("private provider secret")
    monkeypatch.setattr(wikidata_relations, "propose_for_person", fail)
    response = api.post("/persons/1/relations/wikidata")
    assert response.status_code == 503 and "secret" not in response.text


def test_wikidata_dry_run_and_date_precision(session):
    from library.wikidata_relations import propose_for_person, qualifier_date
    data = {"Q1": {"claims": {"P26": [claim("Q2")]}}, "Q2": {}}
    result = propose_for_person(session, 1, apply=False, fetch=lambda ids: {i: data[i] for i in ids})
    assert len(result["proposals"]) == 1 and not session.scalar(select(EntityRelation))
    assert qualifier_date({"qualifiers": {"P580": [{"datavalue": {"value": {
        "time": "+1900-00-00T00:00:00Z", "precision": 8}}}]}}, "P580") is None


def test_migration_and_constraints_in_memory():
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from alembic.script import ScriptDirectory
    from sqlalchemy import inspect
    from sqlalchemy.exc import IntegrityError
    engine = make_engine()
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE llm_models (model_id TEXT UNIQUE, label TEXT, provider TEXT, "
                                "external BOOLEAN, verified BOOLEAN, status TEXT)"))
        revision = ScriptDirectory("alembic").get_revision("e4b8c2a79061")
        with Operations.context(MigrationContext.configure(connection)):
            revision.module.upgrade()
            assert len(inspect(connection).get_indexes("entity_relations")) == 7
            assert len(inspect(connection).get_indexes("entity_relation_evidence")) == 2
            assert connection.scalar(text("SELECT model_id FROM llm_models")) == "openrouter/google/gemma-4-31b-it"
            with pytest.raises(IntegrityError):
                connection.execute(text("INSERT INTO entity_relations (subject_person_id, subject_organization_id, "
                                        "object_person_id, relation, detection_method) VALUES (1, 1, 2, 'rodzic', 'llm')"))
            with pytest.raises(IntegrityError):
                connection.execute(text("INSERT INTO entity_relations (subject_person_id, object_person_id, relation, "
                                        "detection_method, valid_from, valid_to) "
                                        "VALUES (1, 2, 'rodzic', 'llm', '2025-01-01', '2024-01-01')"))
            revision.module.downgrade()
            assert "entity_relations" not in inspect(connection).get_table_names()


def test_country_resolution_handles_inflected_text(session):
    from library.entity_relations_detect import candidates, resolve_candidate
    entries = candidates(session, 10, "w Polsce")
    assert resolve_candidate(session, entries, "Polsce", "country") == COUNTRY


def test_detection_preserves_alias_context_and_explicit_period(session):
    from library.entity_relations_detect import detect_for_document
    session.add(PersonAlias(person_id=1, alias="Świt"))
    session.get(DocumentPerson, 1).raw_mention = "Świt"
    session.get(Document, 10).text = "Świt pracuje w Ministerstwo od 2020-01-01 do 2021-12-31."
    existing, _ = svc.manual_create(session, P1, "pracownik", O1,
                                    valid_from="2000-01-01", valid_to="2005-01-01")
    payloads = []

    def ask(query, model, **kwargs):
        payload = json.loads(query)
        payloads.append(payload)
        if "proposals" in payload:
            return '{"verdicts": []}'
        return json.dumps({"relations": [dict(subject="Świt", subject_type="osoba", relation="pracownik",
            object="Ministerstwo", object_type="organizacja", claim="fakt", quote=payload["text"],
            valid_from="2020-01-01", valid_to="2021-12-31")]})
    result = detect_for_document(session, 10, model="fake", ask=ask)
    assert payloads[0]["known_relations"][0]["subject"] == "Ada Brzask"
    assert result["created"] == 1
    row = session.scalar(select(EntityRelation).where(EntityRelation.id != existing.id))
    assert row.valid_from == datetime.date(2020, 1, 1) and row.valid_to == datetime.date(2021, 12, 31)


def test_graph_incoming_person_for_document_organization(session):
    from library.entity_relations_graph import extend_relationship_graph
    row, _, _ = svc.upsert_relation(session, P2, "pracownik", O1)
    nodes, edges = [], []
    extend_relationship_graph(session, SimpleNamespace(id=10, published_on=None), nodes, edges)
    assert not edges  # a proposal about someone the document does not mention stays off the graph
    svc.decide_relation(session, row, "confirmed")
    extend_relationship_graph(session, SimpleNamespace(id=10, published_on=None), nodes, edges)
    assert {n["id"] for n in nodes} == {"person:2", "organization:1"}
    assert len(edges) == 1
