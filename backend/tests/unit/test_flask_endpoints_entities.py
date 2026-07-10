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
                            with patch("library.entity_service.get_document_entities", return_value=GROUPED):
                                resp = client.post("/website_entities", data={"id": "42"}, headers=API_HEADERS)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert data["refreshed"] == 2
        assert data["place_tags"] == ["miejsce-kijow"]
        assert data["persons_linked"] == 1
        assert data["entities"] == GROUPED
        mock_refresh.assert_called_once_with(session, 42, "# Artykuł o Tusku")
        mock_verify.assert_called_once_with(session, doc, "# Artykuł o Tusku")
        mock_persons.assert_called_once_with(session, doc, "# Artykuł o Tusku")
        assert session.commit.call_count == 3

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
