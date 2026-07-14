"""Unit tests for the /tags and /sources autocomplete endpoints."""

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


class TestTagsList:
    def test_aggregates_and_sorts_by_usage(self, client):
        session = MagicMock()
        session.execute.return_value.scalars.return_value.all.return_value = [
            "geopolityka,kraj-polska",
            "geopolityka, energetyka",
            "geopolityka",
        ]
        with patch("server.get_scoped_session", return_value=session):
            resp = client.get("/tags", headers=API_HEADERS)

        assert resp.status_code == 200
        tags = resp.get_json()["tags"]
        assert tags[0] == {"tag": "geopolityka", "count": 3}
        assert {"tag": "energetyka", "count": 1} in tags
        assert {"tag": "kraj-polska", "count": 1} in tags

    def test_empty_database(self, client):
        session = MagicMock()
        session.execute.return_value.scalars.return_value.all.return_value = []
        with patch("server.get_scoped_session", return_value=session):
            resp = client.get("/tags", headers=API_HEADERS)
        assert resp.status_code == 200
        assert resp.get_json()["tags"] == []


def _source_row(id_, name, count, is_active=True, description=None, url=None):
    row = MagicMock()
    row.id = id_
    row.name = name
    row.description = description
    row.url = url
    row.is_active = is_active
    return (row, count)


class TestSourcesList:
    def test_returns_sources_with_counts(self, client):
        session = MagicMock()
        session.execute.return_value.all.return_value = [
            _source_row(1, "unknow.news", 120), _source_row(2, "own", 80),
        ]
        with patch("server.get_scoped_session", return_value=session):
            resp = client.get("/sources", headers=API_HEADERS)

        assert resp.status_code == 200
        sources = resp.get_json()["sources"]
        # Backward-compat keys consumed by the editor autocomplete.
        assert sources[0]["source"] == "unknow.news"
        assert sources[0]["count"] == 120
        # Lookup-table fields.
        assert sources[0]["name"] == "unknow.news"
        assert sources[0]["id"] == 1
        assert sources[0]["is_active"] is True
        assert sources[1]["source"] == "own"
