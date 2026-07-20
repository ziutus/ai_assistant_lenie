"""Unit tests for the GET /languages endpoint."""

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("flask")

API_HEADERS = {"x-api-key": "test-api-key"}


@pytest.fixture()
def client():
    """Flask test client with auth bypassed (same pattern as test_flask_endpoints_orm)."""
    import server
    server.app.config["TESTING"] = True
    with patch.object(server, "check_auth_header"):
        with server.app.test_client() as c:
            yield c


def _row(code="pl", name_pl="polski"):
    row = MagicMock()
    row.code = code
    row.name_pl = name_pl
    return row


class TestLanguagesList:
    def test_returns_languages_with_document_counts(self, client):
        session = MagicMock()
        session.execute.return_value.all.return_value = [
            (_row("pl", "polski"), 8181),
            (_row("en", "angielski"), 164),
        ]
        with patch("server.get_scoped_session", return_value=session):
            resp = client.get("/languages", headers=API_HEADERS)

        assert resp.status_code == 200
        assert resp.get_json()["languages"] == [
            {"code": "pl", "name_pl": "polski", "count": 8181},
            {"code": "en", "name_pl": "angielski", "count": 164},
        ]

    def test_language_with_no_documents_yet_has_zero_count(self, client):
        session = MagicMock()
        session.execute.return_value.all.return_value = [(_row("lt", "litewski"), 0)]
        with patch("server.get_scoped_session", return_value=session):
            resp = client.get("/languages", headers=API_HEADERS)

        assert resp.get_json()["languages"] == [{"code": "lt", "name_pl": "litewski", "count": 0}]
