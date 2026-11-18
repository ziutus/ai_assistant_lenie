"""Person <-> country / macro-region ties: service, tag matching and REST (in-memory SQLite)."""

import datetime
from types import SimpleNamespace

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("flask")

import flask
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from library import person_territories as svc
from library import person_territory_routes as routes
from library.db.engine import Base
from library.db.models import Document, DocumentPerson, Person, PersonAlias, PersonTerritory
from tests.unit.geo_sqlite_support import make_engine

UNTYPED = (Person, PersonAlias, Document, DocumentPerson)


@pytest.fixture
def session():
    engine = make_engine()
    Base.metadata.create_all(engine, tables=[PersonTerritory.__table__])
    with engine.begin() as conn:
        for model in UNTYPED:
            columns = ["id INTEGER PRIMARY KEY"] + [c.name for c in model.__table__.columns if c.name != "id"]
            conn.execute(text(f"CREATE TABLE {model.__tablename__} ({', '.join(columns)})"))
        conn.execute(text("INSERT INTO persons (id, canonical_name, role, kind) VALUES "
                          "(1, 'Ali Abdullah Salih', 'były prezydent Jemenu', 'public'), "
                          "(2, 'Madżed Abdullah al-Nuzajli', 'rzecznik Sił Zbrojnych Jemenu', 'public'), "
                          "(3, 'Joe Biden', NULL, NULL)"))
        conn.execute(text("INSERT INTO person_aliases (id, person_id, alias) VALUES "
                          "(1, 1, 'Salech'), (2, 1, 'Salecha'), (3, 2, 'Magit Al Nazili')"))
        conn.execute(text("INSERT INTO documents (id, tags, document_type) VALUES "
                          "(10, 'bliski-wschód,kraj-jemen,kraj-iran,miejsce-bliski-wschod,miejsce-europa', 'webpage'), "
                          "(11, 'kraj-jemen,kraj-arabia-saudyjska', 'webpage'), (12, 'kraj-polska', 'webpage')"))
        conn.execute(text("INSERT INTO document_persons (id, document_id, person_id, raw_mention) VALUES "
                          "(1, 10, 1, 'Salech'), (2, 11, 1, 'Salech'), (3, 11, 2, 'Magit Al Nazili')"))
    with sessionmaker(bind=engine)() as db:
        yield db


class TestTags:
    def test_territories_are_read_from_kraj_and_region_tags(self):
        tags = "bliski-wschód,kraj-jemen,KRAJ-Iran,miejsce-bliski-wschod,miejsce-europa,kraj-atlantyda,miejsce-sahel"
        assert svc.territories_of_tags(tags) == {
            ("country", "jemen"), ("country", "iran"), ("region", "bliski-wschod"), ("region", "sahel")}

    def test_list_input_empty_and_garbage(self):
        assert svc.territories_of_tags(["kraj-jemen", 5, None]) == {("country", "jemen")}
        assert svc.territories_of_tags(None) == set() and svc.territories_of_tags("") == set()

    def test_names_and_tags(self):
        assert svc.territory_name("country", "jemen") == "Jemen"
        assert svc.territory_name("region", "bliski-wschod") == "Bliski Wschód"
        assert svc.territory_name("region", "jemen") is None and svc.territory_name("planet", "x") is None
        assert svc.territory_tag("country", "jemen") == "kraj-jemen"
        assert svc.territory_tag("region", "bliski-wschod") == "miejsce-bliski-wschod"


class TestRegionSlugs:
    def test_region_slugs_match_the_miejsce_tags_place_verification_writes(self):
        from library.geopolitical_region_gazetteer import known_geopolitical_regions
        from library.place_verification import _slugify

        regions = known_geopolitical_regions()
        assert len(regions) >= 10 and len({r["slug"] for r in regions}) == len(regions)
        assert all(r["slug"] == _slugify(r["name_pl"]) for r in regions)
        assert {"slug": "bliski-wschod", "name_pl": "Bliski Wschód"} in regions


class TestAddListRemove:
    def test_add_country_and_region_ties(self, session):
        tie, created = svc.add_territory(session, 1, "country", "Jemen", "citizen_of", note="  prezydent 1978–2012 ")
        assert created and tie["name_pl"] == "Jemen" and tie["tag"] == "kraj-jemen"
        assert tie["relation_label"] == "obywatelstwo" and tie["note"] == "prezydent 1978–2012"
        region, _ = svc.add_territory(session, 1, "region", "bliski-wschod", "active_in")
        assert region["name_pl"] == "Bliski Wschód" and region["tag"] == "miejsce-bliski-wschod"
        assert [t["kind"] for t in svc.list_territories(session, 1)] == ["country", "region"]

    def test_readding_a_tie_refreshes_note_and_dates_instead_of_duplicating(self, session):
        svc.add_territory(session, 2, "country", "jemen", "holds_office_in")
        tie, created = svc.add_territory(session, 2, "country", "jemen", "holds_office_in",
                                         note="rzecznik", valid_from="2026-01-01")
        assert not created and tie["note"] == "rzecznik" and tie["valid_from"] == "2026-01-01"
        assert len(svc.list_territories(session, 2)) == 1
        # one person may hold several relations to one country
        svc.add_territory(session, 2, "country", "jemen", "citizen_of")
        assert len(svc.list_territories(session, 2)) == 2

    @pytest.mark.parametrize("args", [
        ("planet", "jemen", "citizen_of"), ("country", "atlantyda", "citizen_of"), ("country", "", "citizen_of"),
        ("region", "jemen", "citizen_of"), ("country", "jemen", "friend_of"), ("region", "kraj-jemen", "active_in"),
    ])
    def test_rejects_unknown_kind_slug_or_relation(self, session, args):
        with pytest.raises(ValueError):
            svc.add_territory(session, 1, *args)

    def test_rejects_bad_or_reversed_dates(self, session):
        with pytest.raises(ValueError, match="ISO date"):
            svc.add_territory(session, 1, "country", "jemen", "citizen_of", valid_from="wczoraj")
        with pytest.raises(ValueError, match="earlier"):
            svc.add_territory(session, 1, "country", "jemen", "citizen_of", valid_from="2012-01-01", valid_to="2011-01-01")

    def test_remove_only_the_persons_own_tie(self, session):
        tie, _ = svc.add_territory(session, 1, "country", "jemen", "citizen_of")
        assert not svc.remove_territory(session, 2, tie["id"])
        assert svc.remove_territory(session, 1, tie["id"]) and svc.list_territories(session, 1) == []
        assert not svc.remove_territory(session, 1, 999)


class TestSuggestions:
    def test_territories_of_the_persons_documents_minus_attached(self, session):
        svc.add_territory(session, 1, "country", "jemen", "citizen_of")
        suggestions = svc.territory_suggestions(session, 1)
        found = {(s["kind"], s["slug"]): s["documents"] for s in suggestions}
        assert found == {("country", "iran"): 1, ("region", "bliski-wschod"): 1, ("country", "arabia-saudyjska"): 1}
        assert ("country", "jemen") not in found and all(s["name_pl"] for s in suggestions)


class TestPersonsForTerritories:
    def prepare(self, session):
        svc.add_territory(session, 1, "country", "jemen", "citizen_of")
        svc.add_territory(session, 1, "country", "jemen", "holds_office_in", valid_to="2012-02-27")
        svc.add_territory(session, 2, "country", "jemen", "holds_office_in", valid_from="2026-01-01")
        svc.add_territory(session, 3, "country", "stany-zjednoczone", "citizen_of")
        svc.add_territory(session, 2, "region", "bliski-wschod", "active_in")

    def test_people_of_a_country_with_aliases_and_each_person_once(self, session):
        self.prepare(session)
        people = svc.persons_for_territories(session, {("country", "jemen"), ("region", "bliski-wschod")})
        assert [p["canonical_name"] for p in people] == ["Ali Abdullah Salih", "Madżed Abdullah al-Nuzajli"]
        salih, nuzajli = people
        assert sorted(salih["aliases"]) == ["Salech", "Salecha"] and len(salih["ties"]) == 2
        assert len(nuzajli["ties"]) == 2 and nuzajli["role"] == "rzecznik Sił Zbrojnych Jemenu"

    def test_a_date_keeps_only_ties_valid_then(self, session):
        self.prepare(session)
        in_2010 = {p["canonical_name"]: [t["relation"] for t in p["ties"]]
                   for p in svc.persons_for_territories(session, {("country", "jemen")}, on=datetime.date(2010, 6, 1))}
        assert in_2010 == {"Ali Abdullah Salih": ["citizen_of", "holds_office_in"]}
        in_2026 = {p["canonical_name"]: [t["relation"] for t in p["ties"]]
                   for p in svc.persons_for_territories(session, {("country", "jemen")}, on=datetime.date(2026, 6, 1))}
        assert in_2026 == {"Ali Abdullah Salih": ["citizen_of"], "Madżed Abdullah al-Nuzajli": ["holds_office_in"]}

    def test_no_territories_no_people(self, session):
        assert svc.persons_for_territories(session, set()) == []

    def test_a_document_resolves_to_its_territories_and_their_people(self, session):
        self.prepare(session)
        result = svc.persons_for_document(session, 10)
        assert [t["tag"] for t in result["territories"]] == ["kraj-iran", "kraj-jemen", "miejsce-bliski-wschod"]
        assert {p["canonical_name"] for p in result["persons"]} == {"Ali Abdullah Salih", "Madżed Abdullah al-Nuzajli"}
        assert svc.persons_for_document(session, 12)["persons"] == []
        assert svc.persons_for_document(session, 999) is None


@pytest.fixture
def api(session, monkeypatch):
    app = flask.Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(routes.bp)

    @app.before_request
    def auth():
        kind = flask.request.headers.get("X-Kind", "service")
        flask.g.auth = SimpleNamespace(kind=kind)

    monkeypatch.setattr(routes, "get_scoped_session", lambda: session)
    return app.test_client()


class TestRoutes:
    def test_get_lists_ties_suggestions_and_choices(self, api, session):
        svc.add_territory(session, 1, "country", "jemen", "citizen_of")
        data = api.get("/persons/1/territories", headers={"X-Kind": "read_only"}).get_json()
        assert [t["slug"] for t in data["territories"]] == ["jemen"]
        assert {s["slug"] for s in data["suggestions"]} == {"iran", "bliski-wschod", "arabia-saudyjska"}
        assert data["relations"]["holds_office_in"] and any(r["slug"] == "sahel" for r in data["regions"])
        assert api.get("/persons/999/territories").status_code == 404

    def test_post_creates_then_updates_and_validates(self, api):
        body = {"kind": "region", "slug": "bliski-wschod", "relation": "active_in", "note": "komentator"}
        first = api.post("/persons/2/territories", json=body)
        assert first.status_code == 201 and first.get_json()["territory"]["tag"] == "miejsce-bliski-wschod"
        assert api.post("/persons/2/territories", json=body | {"note": "inna"}).status_code == 200
        assert api.post("/persons/2/territories", json=body | {"slug": "atlantyda"}).status_code == 400
        assert api.post("/persons/2/territories", json=body | {"valid_to": "jutro"}).status_code == 400
        assert api.post("/persons/999/territories", json=body).status_code == 404
        assert api.post("/persons/2/territories", data="x", content_type="text/plain").status_code == 400

    def test_validation_errors_answer_a_fixed_text_not_the_exception_message(self, api):
        # the slug is echoed in the service exception ("unknown country slug: 'zzz'"), but never in the answer
        response = api.post("/persons/1/territories", json={"kind": "country", "slug": "zzz", "relation": "citizen_of"})
        assert response.status_code == 400
        assert response.get_json()["message"] == svc.ERROR_MESSAGES["slug"] and "zzz" not in response.get_data(as_text=True)
        for body, code in (({"kind": "planet", "slug": "jemen", "relation": "citizen_of"}, "kind"),
                           ({"kind": "country", "slug": "jemen", "relation": "friend"}, "relation"),
                           ({"kind": "country", "slug": "jemen", "relation": "citizen_of", "valid_from": "x"}, "date_format"),
                           ({"kind": "country", "slug": "jemen", "relation": "citizen_of",
                             "valid_from": "2012-01-02", "valid_to": "2012-01-01"}, "date_order")):
            assert api.post("/persons/1/territories", json=body).get_json()["message"] == svc.ERROR_MESSAGES[code]

    def test_writes_need_a_user_or_service_key(self, api):
        body = {"kind": "country", "slug": "jemen", "relation": "citizen_of"}
        assert api.post("/persons/1/territories", json=body, headers={"X-Kind": "read_only"}).status_code == 403
        assert api.post("/persons/1/territories", json=body, headers={"X-Kind": "user"}).status_code == 201
        assert api.delete("/persons/1/territories/1", headers={"X-Kind": "read_only"}).status_code == 403

    def test_delete(self, api, session):
        tie, _ = svc.add_territory(session, 1, "country", "jemen", "citizen_of")
        assert api.delete(f"/persons/1/territories/{tie['id']}").status_code == 200
        assert api.delete(f"/persons/1/territories/{tie['id']}").status_code == 404

    def test_people_of_a_territory(self, api, session):
        svc.add_territory(session, 2, "country", "jemen", "holds_office_in", valid_from="2026-01-01")
        data = api.get("/territories/country/jemen/persons").get_json()
        assert data["name_pl"] == "Jemen" and [p["canonical_name"] for p in data["persons"]] == ["Madżed Abdullah al-Nuzajli"]
        assert api.get("/territories/country/jemen/persons?on=2020-01-01").get_json()["persons"] == []
        assert api.get("/territories/country/jemen/persons?on=nie").status_code == 400
        assert api.get("/territories/country/atlantyda/persons").status_code == 404
        assert api.get("/territories/city/jemen/persons").status_code == 404

    def test_document_territory_persons(self, api, session):
        svc.add_territory(session, 1, "country", "jemen", "citizen_of")
        data = api.get("/document/10/territory_persons").get_json()
        assert [t["tag"] for t in data["territories"]] == ["kraj-iran", "kraj-jemen", "miejsce-bliski-wschod"]
        assert [p["canonical_name"] for p in data["persons"]] == ["Ali Abdullah Salih"]
        assert api.get("/document/999/territory_persons").status_code == 404
