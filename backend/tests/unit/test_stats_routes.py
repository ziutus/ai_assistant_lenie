"""Unit tests for GET /stats (document counts by type/state/source + recent daily ingestion)."""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("flask")

API_HEADERS = {"x-api-key": "test-api-key"}


@pytest.fixture()
def client():
    """Flask test client with auth bypassed (same pattern as test_flask_endpoints_document_states)."""
    import server
    server.app.config["TESTING"] = True
    with patch.object(server, "check_auth_header"):
        with server.app.test_client() as c:
            yield c


def _row(**kwargs):
    row = MagicMock()
    for key, value in kwargs.items():
        setattr(row, key, value)
    return row


def _session_with(total, by_type, by_state, by_source, daily, recent):
    """Build a MagicMock session whose session.execute() calls, in the order
    issued by stats_routes.stats(), return the given result sets."""
    session = MagicMock()
    total_result = MagicMock(scalar_one=MagicMock(return_value=total))
    by_type_result = MagicMock(all=MagicMock(return_value=by_type))
    by_state_result = MagicMock(all=MagicMock(return_value=by_state))
    by_source_result = MagicMock(all=MagicMock(return_value=by_source))
    daily_result = MagicMock(all=MagicMock(return_value=daily))
    recent_result = MagicMock(all=MagicMock(return_value=recent))
    session.execute.side_effect = [
        total_result, by_type_result, by_state_result, by_source_result, daily_result, recent_result,
    ]
    return session


class TestStats:
    def test_returns_expected_shape(self, client):
        session = _session_with(
            total=3,
            by_type=[_row(document_type="webpage", count=2), _row(document_type="link", count=1)],
            by_state=[_row(processing_status="EMBEDDING_EXIST", count=3)],
            by_source=[_row(name="own", count=3)],
            daily=[],
            recent=[_row(id=1, title="T", document_type="webpage", processing_status="EMBEDDING_EXIST",
                          name="own", ingested_at=None)],
        )
        with patch("library.stats_routes.get_scoped_session", return_value=session):
            resp = client.get("/stats", headers=API_HEADERS)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert data["total"] == 3
        assert data["by_type"] == [{"document_type": "webpage", "count": 2}, {"document_type": "link", "count": 1}]
        assert data["by_state"] == [{"processing_status": "EMBEDDING_EXIST", "count": 3}]
        assert data["by_source"] == [{"name": "own", "count": 3}]
        assert len(data["daily"]) == 30  # default window
        assert data["recent"] == [{
            "id": 1, "title": "T", "document_type": "webpage", "processing_status": "EMBEDDING_EXIST",
            "source": "own", "ingested_at": None,
        }]

    def test_days_param_zero_fills_and_orders(self, client):
        today = date.today()
        session = _session_with(total=0, by_type=[], by_state=[], by_source=[],
                                 daily=[_row(day=str(today), count=2)], recent=[])
        with patch("library.stats_routes.get_scoped_session", return_value=session):
            resp = client.get("/stats?days=3", headers=API_HEADERS)

        assert resp.status_code == 200
        data = resp.get_json()
        expected_days = [(today - timedelta(days=i)).isoformat() for i in (2, 1, 0)]
        assert [d["day"] for d in data["daily"]] == expected_days
        assert data["daily"][-1]["count"] == 2
        assert data["daily"][0]["count"] == 0

    def test_days_zero_returns_400(self, client):
        resp = client.get("/stats?days=0", headers=API_HEADERS)
        assert resp.status_code == 400

    def test_days_over_max_returns_400(self, client):
        resp = client.get("/stats?days=9999", headers=API_HEADERS)
        assert resp.status_code == 400


class TestStatsAuth:
    def test_missing_api_key_returns_401(self):
        import server
        server.app.config["TESTING"] = True
        with server.app.test_client() as c:
            resp = c.get("/stats")
            assert resp.status_code == 401
