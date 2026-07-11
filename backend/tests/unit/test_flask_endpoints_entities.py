"""Unit tests for the /website_entities endpoints (GET read, POST refresh)."""

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("flask")

API_HEADERS = {"x-api-key": "test-api-key"}

GROUPED = {
    "persName": [{"text": "Tusk", "count": 2}],
    "geogName": [{"text": "cieśnina Ormuz", "count": 1}],
    "placeName": [],
}


@pytest.fixture()
def client():
    """Flask test client with auth bypassed (same pattern as test_flask_endpoints_orm)."""
    import server
    server.app.config["TESTING"] = True
    with patch.object(server, "check_auth_header"):
        with server.app.test_client() as c:
            yield c


class TestWebsiteEntitiesGet:
    def test_missing_id_returns_400(self, client):
        resp = client.get("/website_entities", headers=API_HEADERS)
        assert resp.status_code == 400

    @pytest.mark.parametrize("bad_id", ["abc", "0", "-5"])
    def test_invalid_id_returns_400(self, client, bad_id):
        resp = client.get(f"/website_entities?id={bad_id}", headers=API_HEADERS)
        assert resp.status_code == 400

    def test_document_not_found_returns_404(self, client):
        with patch("server.get_scoped_session", return_value=MagicMock()):
            with patch("server.WebDocument") as MockDoc:
                MockDoc.get_by_id.return_value = None
                resp = client.get("/website_entities?id=42", headers=API_HEADERS)
        assert resp.status_code == 404

    def test_returns_grouped_entities(self, client):
        with patch("server.get_scoped_session", return_value=MagicMock()):
            with patch("server.WebDocument") as MockDoc:
                MockDoc.get_by_id.return_value = MagicMock()
                with patch("library.entity_service.get_document_entities", return_value=GROUPED):
                    resp = client.get("/website_entities?id=42", headers=API_HEADERS)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert data["id"] == 42
        assert data["entities"] == GROUPED


class TestWebsiteEntitiesRefresh:
    def test_missing_id_returns_400(self, client):
        resp = client.post("/website_entities", data={}, headers=API_HEADERS)
        assert resp.status_code == 400

    def test_document_without_text_returns_400(self, client):
        doc = MagicMock(text_md=None, text=None)
        with patch("server.get_scoped_session", return_value=MagicMock()):
            with patch("server.WebDocument") as MockDoc:
                MockDoc.get_by_id.return_value = doc
                resp = client.post("/website_entities", data={"id": "42"}, headers=API_HEADERS)
        assert resp.status_code == 400

    def test_refreshes_verifies_and_returns_entities(self, client):
        doc = MagicMock(text_md="# Artykuł o Tusku", text=None)
        session = MagicMock()
        with patch("server.get_scoped_session", return_value=session):
            with patch("server.WebDocument") as MockDoc:
                MockDoc.get_by_id.return_value = doc
                with patch("library.entity_service.refresh_document_entities", return_value=[MagicMock()] * 2) as mock_refresh:
                    with patch("library.place_verification.verify_document_places",
                               return_value={"checked": 1, "resolved": ["Kijów"], "tagged": ["miejsce-kijow"]}) as mock_verify:
                        with patch("library.person_registry.resolve_document_persons",
                                   return_value={"linked": [("Tusk", "Donald Tusk", "wikidata_matched")], "skipped": []}) as mock_persons:
                            with patch("library.overpass_client.attach_document_pipelines",
                                       return_value={"checked": 1, "resolved": ["Baltic Pipe"]}) as mock_pipes:
                                with patch("library.entity_service.get_document_entities", return_value=GROUPED):
                                    resp = client.post("/website_entities", data={"id": "42"}, headers=API_HEADERS)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert data["refreshed"] == 2
        assert data["place_tags"] == ["miejsce-kijow"]
        assert data["persons_linked"] == 1
        assert data["pipelines"] == ["Baltic Pipe"]
        assert data["entities"] == GROUPED
        mock_refresh.assert_called_once_with(session, 42, "# Artykuł o Tusku")
        mock_verify.assert_called_once_with(session, doc, "# Artykuł o Tusku")
        mock_persons.assert_called_once_with(session, doc, "# Artykuł o Tusku")
        mock_pipes.assert_called_once_with(session, 42)
        assert session.commit.call_count == 4  # refresh + miejsca + osoby + rurociągi

    def test_place_verification_failure_does_not_fail_request(self, client):
        doc = MagicMock(text_md="# Artykuł", text=None)
        session = MagicMock()
        with patch("server.get_scoped_session", return_value=session):
            with patch("server.WebDocument") as MockDoc:
                MockDoc.get_by_id.return_value = doc
                with patch("library.entity_service.refresh_document_entities", return_value=[MagicMock()]):
                    with patch("library.place_verification.verify_document_places", side_effect=RuntimeError("boom")):
                        with patch("library.person_registry.resolve_document_persons",
                                   return_value={"linked": [], "skipped": []}):
                            with patch("library.entity_service.get_document_entities", return_value=GROUPED):
                                resp = client.post("/website_entities", data={"id": "42"}, headers=API_HEADERS)

        assert resp.status_code == 200
        assert resp.get_json()["place_tags"] == []
        session.rollback.assert_called_once()


class TestWebsiteEntitiesDelete:
    def test_entity_not_found_returns_404(self, client):
        session = MagicMock()
        session.get.return_value = None
        with patch("server.get_scoped_session", return_value=session):
            resp = client.delete("/website_entities/999", headers=API_HEADERS)
        assert resp.status_code == 404

    def test_deletes_place_entity_without_person_link(self, client):
        entity = MagicMock(entity_type="geogName", entity_text="Starling", document_id=42)
        session = MagicMock()
        session.get.return_value = entity
        with patch("server.get_scoped_session", return_value=session):
            resp = client.delete("/website_entities/7", headers=API_HEADERS)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["deleted_entity_id"] == 7
        assert data["person_link_removed"] is False
        session.delete.assert_called_once_with(entity)
        session.commit.assert_called_once()

    def test_person_entity_removes_matching_link(self, client):
        entity = MagicMock(entity_type="persName", entity_text="Starling", document_id=42)
        link = MagicMock()
        session = MagicMock()
        session.get.return_value = entity
        session.execute.return_value.scalars.return_value.first.return_value = link
        with patch("server.get_scoped_session", return_value=session):
            with patch("library.person_registry.reject_review_link",
                       return_value={"action": "reject", "person_deleted": True}) as mock_reject:
                resp = client.delete("/website_entities/7", headers=API_HEADERS)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["person_link_removed"] is True
        assert data["person_deleted"] is True
        mock_reject.assert_called_once_with(session, link)
        session.delete.assert_called_once_with(entity)


class TestDocumentPersonsDecide:
    def test_link_not_found_returns_404(self, client):
        session = MagicMock()
        session.get.return_value = None
        with patch("server.get_scoped_session", return_value=session):
            resp = client.patch("/document_persons/999", json={"action": "reject"}, headers=API_HEADERS)
        assert resp.status_code == 404

    def test_invalid_action_returns_400(self, client):
        resp = client.patch("/document_persons/1", json={"action": "frobnicate"}, headers=API_HEADERS)
        assert resp.status_code == 400

    def test_reject_works_for_confident_link(self, client):
        """Editor path: no 409 gate — a wrong wikidata_matched link can be undone."""
        link = MagicMock(confidence="wikidata_matched")
        session = MagicMock()
        session.get.return_value = link
        with patch("server.get_scoped_session", return_value=session):
            with patch("library.person_registry.reject_review_link",
                       return_value={"action": "reject", "link_id": 1, "person_id": 5,
                                     "person_deleted": False}) as mock_reject:
                resp = client.patch("/document_persons/1", json={"action": "reject"}, headers=API_HEADERS)

        assert resp.status_code == 200
        assert resp.get_json()["action"] == "reject"
        mock_reject.assert_called_once_with(session, link)
        session.commit.assert_called_once()

    def test_review_queue_endpoint_still_gates_on_manual_review(self, client):
        link = MagicMock(confidence="wikidata_matched")
        session = MagicMock()
        session.get.return_value = link
        with patch("server.get_scoped_session", return_value=session):
            resp = client.patch("/persons_review/1", json={"action": "reject"}, headers=API_HEADERS)
        assert resp.status_code == 409


class TestPersonAliasAdd:
    def test_missing_alias_returns_400(self, client):
        resp = client.post("/persons/1/aliases", json={}, headers=API_HEADERS)
        assert resp.status_code == 400

    def test_person_not_found_returns_404(self, client):
        session = MagicMock()
        session.get.return_value = None
        with patch("server.get_scoped_session", return_value=session):
            resp = client.post("/persons/999/aliases", json={"alias": "Starlinek"}, headers=API_HEADERS)
        assert resp.status_code == 404

    def test_adds_alias(self, client):
        person = MagicMock()
        person.aliases = [MagicMock(alias="Starlinek")]
        session = MagicMock()
        session.get.return_value = person
        with patch("server.get_scoped_session", return_value=session):
            with patch("library.person_registry.add_person_alias", return_value=True) as mock_add:
                resp = client.post("/persons/5/aliases", json={"alias": "Starlinek"}, headers=API_HEADERS)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["added"] is True
        assert data["aliases"] == ["Starlinek"]
        mock_add.assert_called_once_with(session, person, "Starlinek")
        session.commit.assert_called_once()
