"""Registry of concepts (conceptName entities): canonical entries with aliases, mention decisions by (document,
normalized name), the unlinked queue with suggestions and the auto-link of a fresh mention. In-memory SQLite;
trigram similarity and foreign-key enforcement are PostgreSQL-only and not exercised here.
"""

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("flask")

from flask import Flask
from sqlalchemy import Integer, String, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from library import concept_routes
from library import concept_service as svc
from library.db.engine import Base
from library.db.models import Concept, ConceptAlias, ConceptMentionLink, DocumentEntity
from tests.unit.geo_sqlite_support import make_engine


class _StubBase(DeclarativeBase):
    pass


class StubDocument(_StubBase):
    __tablename__ = "stub_documents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(100), default="t")


def _add_mention(session, row_id: int, document_id: int, name: str, mentions: int = 1) -> None:
    session.execute(
        text(
            "INSERT INTO document_entities (id, document_id, entity_type, entity_text, mention_count) "
            "VALUES (:i, :d, 'conceptName', :n, :m)"
        ),
        {"i": row_id, "d": document_id, "n": name, "m": mentions},
    )


@pytest.fixture
def session(monkeypatch):
    engine = make_engine()
    Base.metadata.create_all(
        engine, tables=[Concept.__table__, ConceptAlias.__table__, ConceptMentionLink.__table__]
    )
    _StubBase.metadata.create_all(engine)
    with engine.begin() as conn:
        columns = ["id INTEGER PRIMARY KEY"] + [c.name for c in DocumentEntity.__table__.columns if c.name != "id"]
        conn.execute(text(f"CREATE TABLE document_entities ({', '.join(columns)})"))
    monkeypatch.setattr(svc, "Document", StubDocument)
    s = sessionmaker(bind=engine)()
    s.add_all([StubDocument(id=1, title="Doc 1"), StubDocument(id=2, title="Doc 2"), StubDocument(id=3, title="Doc 3")])
    s.commit()
    return s


class TestRegistry:
    def test_create_adds_title_and_aliases(self, session):
        concept, created = svc.create_concept(session, name="Ciemne oświecenie", aliases=["Dark Enlightenment"])
        assert created
        assert sorted(a.alias for a in concept.aliases) == ["Ciemne oświecenie", "Dark Enlightenment"]

    def test_existing_name_returns_the_same_concept(self, session):
        first, _ = svc.create_concept(session, name="Ciemne oświecenie")
        again, created = svc.create_concept(session, name="  ciemne   OŚWIECENIE ")
        assert not created and again.id == first.id

    def test_name_is_required(self, session):
        with pytest.raises(svc.ConceptError):
            svc.create_concept(session, name="   ")

    def test_update_refuses_a_name_of_another_concept(self, session):
        svc.create_concept(session, name="Neoreakcja")
        other, _ = svc.create_concept(session, name="Akceleracjonizm")
        with pytest.raises(svc.ConceptError) as info:
            svc.update_concept(session, other.id, aliases=["neoreakcja"])
        assert info.value.status == 409

    def test_description_can_be_cleared(self, session):
        concept, _ = svc.create_concept(session, name="Neoreakcja", description="Nurt")
        svc.update_concept(session, concept.id, description=None)
        assert concept.description is None

    def test_last_alias_cannot_be_removed(self, session):
        concept, _ = svc.create_concept(session, name="Neoreakcja")
        with pytest.raises(svc.ConceptError):
            svc.remove_alias(session, concept.id, concept.aliases[0].id)


class TestMentions:
    def test_unlinked_queue_groups_by_name_with_alias_suggestion(self, session):
        concept, _ = svc.create_concept(session, name="Ciemne oświecenie")
        _add_mention(session, 1, 1, "Ciemne oświecenie", 3)
        _add_mention(session, 2, 2, "ciemne oświecenie", 2)
        groups, total = svc.unlinked_mentions(session)
        assert total == 1
        assert groups[0]["document_count"] == 2 and groups[0]["mentions"] == 5
        assert groups[0]["suggestions"][0]["concept"]["id"] == concept.id
        assert groups[0]["suggestions"][0]["reason"] == "alias"

    def test_link_removes_the_mention_from_the_queue_and_teaches_the_alias(self, session):
        concept, _ = svc.create_concept(session, name="Ciemne oświecenie")
        _add_mention(session, 1, 1, "Ciemnego oświecenia")
        assert svc.link_mentions(session, "Ciemnego oświecenia", concept.id) == 1
        assert svc.unlinked_mentions(session)[1] == 0
        assert "Ciemnego oświecenia" in [a.alias for a in concept.aliases]
        assert svc.get_concept(session, concept.id)["documents"][0]["surfaces"] == ["Ciemnego oświecenia"]

    def test_link_refuses_a_name_owned_by_another_concept(self, session):
        svc.create_concept(session, name="Neoreakcja")
        other, _ = svc.create_concept(session, name="Akceleracjonizm")
        _add_mention(session, 1, 1, "Neoreakcja")
        with pytest.raises(svc.ConceptError) as info:
            svc.link_mentions(session, "Neoreakcja", other.id)
        assert info.value.status == 409

    def test_reject_hides_the_suggestion_but_not_a_confirmed_link(self, session):
        concept, _ = svc.create_concept(session, name="Neoreakcja", aliases=["NRx"])
        _add_mention(session, 1, 1, "NRx")
        svc.reject_suggestion(session, "NRx", concept.id)
        groups, _ = svc.unlinked_mentions(session)
        assert groups[0]["suggestions"] == []

    def test_unlink_puts_the_mention_back(self, session):
        concept, _ = svc.create_concept(session, name="Neoreakcja")
        _add_mention(session, 1, 1, "Neoreakcja")
        svc.link_mentions(session, "Neoreakcja", concept.id)
        svc.unlink_mentions(session, "Neoreakcja", concept.id)
        assert svc.unlinked_mentions(session)[1] == 1
        with pytest.raises(svc.ConceptError):
            svc.unlink_mentions(session, "Neoreakcja", concept.id)

    def test_from_mention_creates_and_links_in_every_document(self, session):
        _add_mention(session, 1, 1, "Ciemne oświecenie")
        _add_mention(session, 2, 2, "Ciemne oświecenie")
        concept, created, linked = svc.create_concept_from_mention(session, "Ciemne oświecenie")
        assert created and linked == 2
        assert svc.get_concept(session, concept.id)["document_count"] == 2

    def test_from_mention_without_any_mention_is_404(self, session):
        with pytest.raises(svc.ConceptError) as info:
            svc.create_concept_from_mention(session, "Nic")
        assert info.value.status == 404

    def test_auto_link_only_for_an_exact_single_owner(self, session):
        concept, _ = svc.create_concept(session, name="Ciemne oświecenie")
        assert svc.auto_link_mention(session, 3, "ciemne oświecenie") == concept.id
        assert svc.auto_link_mention(session, 3, "ciemne oświecenie") == concept.id  # idempotent
        assert svc.auto_link_mention(session, 3, "Coś innego") is None
        assert session.query(ConceptMentionLink).count() == 1


class TestRoutes:
    @pytest.fixture
    def client(self, session, monkeypatch):
        monkeypatch.setattr(concept_routes, "get_scoped_session", lambda: session)
        app = Flask(__name__)
        app.register_blueprint(concept_routes.bp)
        return app.test_client()

    def test_create_get_patch_delete(self, client):
        created = client.post("/concepts", json={"name": "Ciemne oświecenie", "aliases": ["Dark Enlightenment"]})
        assert created.status_code == 201
        concept_id = created.get_json()["concept"]["id"]
        assert client.post("/concepts", json={"name": "dark enlightenment"}).status_code == 200
        patched = client.patch(f"/concepts/{concept_id}", json={"description": "Nurt myśli politycznej"})
        assert patched.get_json()["concept"]["description"] == "Nurt myśli politycznej"
        assert client.get("/concepts?q=dark").get_json()["total"] == 1
        assert client.delete(f"/concepts/{concept_id}").status_code == 200
        assert client.get(f"/concepts/{concept_id}").status_code == 404

    def test_validation(self, client):
        assert client.post("/concepts", json={}).status_code == 400
        assert client.post("/concepts/mentions/link", json={"name": "x"}).status_code == 400
        assert client.get("/concepts/candidates").status_code == 400
