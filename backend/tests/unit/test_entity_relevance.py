"""Manual entity relevance: API, serialization, replay and place tag gates."""

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("flask")

from library.db.models import Document, DocumentEntity, EntityReviewDecision, GeocodeCache  # noqa: E402
from library.entity_overrides import replay_entity_relevance_decisions  # noqa: E402
from library.entity_service import filter_entities_to_text, get_document_entities  # noqa: E402
from library.place_verification import add_place_tag, remove_orphaned_tag, verify_document_places  # noqa: E402

HEADERS = {"x-api-key": "test-api-key"}


@pytest.fixture()
def client():
    import server

    server.app.config["TESTING"] = True
    with patch.object(server, "check_auth_header"), server.app.test_client() as test_client:
        yield test_client


def entity(kind="placeName", relevance="central", name="Sarajewo", **kwargs):
    return DocumentEntity(id=7, document_id=42, entity_type=kind, entity_text=name, mention_count=2,
                          variants=["Sarajewie"], source="ner", relevance=relevance, **kwargs)


def geocode():
    return GeocodeCache(id=9, query="Sarajewo", display_name="Sarajewo", resolved=True, lat=43.8, lon=18.4)


@pytest.mark.parametrize("body", [{}, {"relevance": "wrong"}, {"relevance": None}, {"relevance": []},
                                  {"relevance": {}}, {"relevance": 1}, [], "central"])
def test_patch_invalid(client, body):
    with patch("server.get_scoped_session") as session:
        response = client.patch("/website_entities/7/relevance", json=body, headers=HEADERS)
    assert response.status_code == 400
    session.return_value.get.assert_not_called()
    session.return_value.commit.assert_not_called()


def test_patch_missing(client):
    session = MagicMock()
    session.get.return_value = None
    with patch("server.get_scoped_session", return_value=session):
        response = client.patch("/website_entities/7/relevance", json={"relevance": "related"}, headers=HEADERS)
    assert response.status_code == 404
    session.commit.assert_not_called()


@pytest.mark.parametrize("kind", ["persName", "placeName", "geogName"])
@pytest.mark.parametrize("relevance", ["central", "related", "figurative"])
def test_patch_saves_audit_and_reconciles_tags_without_changing_source(client, kind, relevance):
    row = entity(kind, "figurative", geocode=geocode(), geocode_id=9)
    doc = Document(id=42, tags="topic,miejsce-sarajewo")
    session = MagicMock()
    session.get.side_effect = lambda model, key: row if model is DocumentEntity else doc
    session.query.return_value.filter.return_value.all.return_value = []
    session.query.return_value.filter.return_value.order_by.return_value.all.return_value = [row]
    with patch("server.get_scoped_session", return_value=session):
        response = client.patch("/website_entities/7/relevance", json={"relevance": relevance}, headers=HEADERS)
    assert response.status_code == 200
    assert response.json["entity"]["relevance"] == relevance
    assert row.source == "ner"
    audit = next(call.args[0] for call in session.add.call_args_list
                 if isinstance(call.args[0], EntityReviewDecision))
    assert audit.decision == "relevance_set"
    assert audit.details == {"relevance": relevance, "variants": ["Sarajewie"]}
    if kind != "persName":
        assert ("miejsce-sarajewo" in doc.tags) == (relevance != "figurative")
    session.commit.assert_called_once()


@pytest.mark.parametrize("relevance", ["central", "related"])
def test_patch_restores_tag(client, relevance):
    row = entity(relevance="figurative", geocode=geocode())
    doc = Document(id=42, tags="topic")
    session = MagicMock()
    session.get.side_effect = lambda model, key: row if model is DocumentEntity else doc
    session.query.return_value.filter.return_value.order_by.return_value.all.return_value = [row]
    with patch("server.get_scoped_session", return_value=session):
        response = client.patch("/website_entities/7/relevance", json={"relevance": relevance}, headers=HEADERS)
    assert response.status_code == 200
    assert doc.tags == "topic,miejsce-sarajewo"


@pytest.mark.parametrize("kind", ["persName", "geogName", "placeName", "orgName", "eventName"])
@pytest.mark.parametrize("relevance", ["central", "related", "figurative"])
def test_read_and_chapter_filter_preserve_relevance(kind, relevance):
    row = entity(kind, relevance)
    session = MagicMock()
    session.query.return_value.filter.return_value.order_by.return_value.all.return_value = [row]
    grouped = get_document_entities(session, 42)
    assert grouped[kind][0]["relevance"] == relevance
    assert filter_entities_to_text(grouped, "W Sarajewie.")[kind][0]["relevance"] == relevance


def decision(id, name, relevance, kind="placeName", variants=None):
    return EntityReviewDecision(id=id, document_id=42, entity_type=kind, entity_text=name,
                                decision="relevance_set", details={"relevance": relevance, "variants": variants or []})


def test_replay_latest_matching_name_or_variant_per_type_and_all_matching_rows():
    rows = [entity(name="Sarajewo"), entity(name="Nowa nazwa"), entity("persName", name="Sarajewo"),
            entity(name="Brak decyzji")]
    # Different fresh names sharing the recorded surface form must both receive the decision.
    rows[-1].variants = []
    session = MagicMock()
    decisions = [decision(1, "SARAJEWO", "figurative"), decision(2, "Sarajewo", "related", "persName"),
                 decision(3, "Inna nazwa", "related", variants=["SARAJEWIE"])]
    session.scalars.return_value.all.side_effect = [decisions, rows]
    replay_entity_relevance_decisions(session, 42)
    assert [row.relevance for row in rows] == ["related", "related", "related", "central"]
    assert all(row.source == "ner" for row in rows)
    session.add.assert_not_called()


def test_replay_removes_tag_added_by_structural_replay():
    row = entity(geocode=geocode())
    doc = Document(id=42, tags="topic,miejsce-sarajewo")
    session = MagicMock()
    session.scalars.return_value.all.side_effect = [[decision(1, "Sarajewo", "figurative")], [row]]
    session.query.return_value.filter.return_value.all.return_value = []
    replay_entity_relevance_decisions(session, 42, doc)
    assert row.relevance == "figurative"
    assert doc.tags == "topic"


@pytest.mark.parametrize("status", [None, "confirmed"])
def test_figurative_place_is_not_verified_or_tagged(status):
    row = entity(relevance="figurative", geocode=geocode(), place_verification_status=status)
    doc = Document(id=42, title="Topic", tags="topic,miejsce-sarajewo")
    session = MagicMock()
    session.query.return_value.filter.return_value.all.return_value = [row]
    with patch("library.place_verification._get_or_create_geocode") as lookup:
        verify_document_places(session, doc, "Sarajewo")
    lookup.assert_not_called()
    assert add_place_tag(doc, row) is None
    assert doc.tags == "topic"


@pytest.mark.parametrize("other_relevance", ["central", "related", "figurative"])
def test_only_nonfigurative_places_support_shared_tags(other_relevance):
    row = entity(relevance="figurative", geocode=geocode())
    other = entity(relevance=other_relevance, geocode=geocode())
    other.id = 8
    doc = Document(id=42, tags="topic,miejsce-sarajewo")
    session = MagicMock()
    session.query.return_value.filter.return_value.all.return_value = [other]
    remove_orphaned_tag(session, doc, row)
    assert ("miejsce-sarajewo" in doc.tags) == (other_relevance != "figurative")
