"""Unit tests for GET /document_states endpoint (Story B-93).

Tests verify that the endpoint returns all enum values from
StalkerDocumentStatus, StalkerDocumentType, and StalkerDocumentStatusError.
"""

from unittest.mock import patch

import pytest

sa = pytest.importorskip("sqlalchemy")

API_HEADERS = {"x-api-key": "test-api-key"}


@pytest.fixture()
def client():
    """Create Flask test client with auth bypassed."""
    import server
    server.app.config["TESTING"] = True
    with patch.object(server, "check_auth_header"):
        with server.app.test_client() as c:
            yield c


class TestDocumentStates:
    def test_returns_200_with_correct_format(self, client):
        """GET /document_states returns HTTP 200 with status, message, encoding, states, types, errors."""
        resp = client.get("/document_states", headers=API_HEADERS)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert data["message"] == "Document states retrieved"
        assert data["encoding"] == "utf8"
        assert "states" in data
        assert "types" in data
        assert "errors" in data

    def test_contains_all_states(self, client):
        """Response contains all values from StalkerDocumentStatus."""
        from library.models.stalker_document_status import StalkerDocumentStatus
        resp = client.get("/document_states", headers=API_HEADERS)
        data = resp.get_json()
        expected = [s.name for s in StalkerDocumentStatus]
        assert len(data["states"]) == len(expected)
        assert set(data["states"]) == set(expected)

    def test_contains_all_types(self, client):
        """Response contains all values from StalkerDocumentType."""
        from library.models.stalker_document_type import StalkerDocumentType
        resp = client.get("/document_states", headers=API_HEADERS)
        data = resp.get_json()
        expected = [t.name for t in StalkerDocumentType]
        assert len(data["types"]) == len(expected)
        assert set(data["types"]) == set(expected)

    def test_contains_all_errors(self, client):
        """Response contains all values from StalkerDocumentStatusError."""
        from library.models.stalker_document_status_error import StalkerDocumentStatusError
        resp = client.get("/document_states", headers=API_HEADERS)
        data = resp.get_json()
        expected = [e.name for e in StalkerDocumentStatusError]
        assert len(data["errors"]) == len(expected)
        assert set(data["errors"]) == set(expected)

    def test_options_returns_200(self, client):
        """OPTIONS /document_states returns HTTP 200 (CORS preflight)."""
        resp = client.options("/document_states", headers=API_HEADERS)
        assert resp.status_code == 200

    def test_states_are_list_of_strings(self, client):
        """All returned values are strings (enum names, not integers)."""
        resp = client.get("/document_states", headers=API_HEADERS)
        data = resp.get_json()
        for state in data["states"]:
            assert isinstance(state, str)
        for t in data["types"]:
            assert isinstance(t, str)
        for e in data["errors"]:
            assert isinstance(e, str)


class TestDocumentStatesAuth:
    def test_missing_api_key_returns_400(self):
        """Missing x-api-key header returns HTTP 400."""
        import server
        server.app.config["TESTING"] = True
        with server.app.test_client() as c:
            resp = c.get("/document_states")
            assert resp.status_code == 400
