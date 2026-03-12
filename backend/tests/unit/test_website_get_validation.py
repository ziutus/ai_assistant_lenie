"""Unit tests for /website_get input validation (Story 31.2).

Tests verify that the Flask handler returns proper HTTP 400 for invalid IDs
(non-numeric, zero, negative) and 404 for nonexistent IDs.

Requires sqlalchemy in the environment (skipped otherwise).
"""

from unittest.mock import patch, MagicMock

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


class TestWebsiteGetValidation:
    def test_non_numeric_id_returns_400(self, client):
        resp = client.get("/website_get?id=abc", headers=API_HEADERS)
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["status"] == "error"
        assert "positive integer" in data["message"]

    def test_negative_id_returns_400(self, client):
        resp = client.get("/website_get?id=-1", headers=API_HEADERS)
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["status"] == "error"
        assert "positive integer" in data["message"]

    def test_zero_id_returns_400(self, client):
        resp = client.get("/website_get?id=0", headers=API_HEADERS)
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["status"] == "error"
        assert "positive integer" in data["message"]

    def test_float_id_returns_400(self, client):
        resp = client.get("/website_get?id=1.5", headers=API_HEADERS)
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["status"] == "error"
        assert "positive integer" in data["message"]

    def test_empty_id_returns_400(self, client):
        """Empty id param (?id=) should be treated as missing → 400."""
        resp = client.get("/website_get?id=", headers=API_HEADERS)
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["status"] == "error"

    def test_missing_id_returns_400(self, client):
        resp = client.get("/website_get", headers=API_HEADERS)
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["status"] == "error"

    def test_nonexistent_id_returns_404(self, client):
        """Valid numeric ID that does not exist in DB should return 404 (AC #1)."""
        with patch("server.WebDocument") as mock_wd:
            mock_wd.get_by_id.return_value = None
            resp = client.get("/website_get?id=999999", headers=API_HEADERS)
        assert resp.status_code == 404
        data = resp.get_json()
        assert data["status"] == "error"
        assert "not found" in data["message"].lower()

    def test_valid_id_returns_document(self, client):
        """Valid ID that exists should return 200 with document data."""
        mock_doc = MagicMock()
        mock_doc.dict.return_value = {"id": 1, "url": "https://example.com"}
        with patch("server.WebDocument") as mock_wd:
            mock_wd.get_by_id.return_value = mock_doc
            resp = client.get("/website_get?id=1", headers=API_HEADERS)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["id"] == 1
