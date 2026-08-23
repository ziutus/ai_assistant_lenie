import datetime as dt
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")

from flask import Flask, g


def _item(status="watchlist"):
    return SimpleNamespace(
        id=17, name="LinkStack", homepage_url="https://github.com/LinkStackOrg/linkstack",
        description="Współdzielona strona z linkami", category="bookmarking", status=status,
        personal_note=None, source_url="https://example.com/awesome", source_context="Awesome Homelab",
        source_document_id=None, source_candidate_id=None, source_document=None,
        created_at=dt.datetime(2026, 8, 23, tzinfo=dt.timezone.utc),
        updated_at=dt.datetime(2026, 8, 23, tzinfo=dt.timezone.utc),
    )


class TestToolRecommendationRoutes:
    def test_create_requires_name(self, monkeypatch):
        from library.tool_recommendation_routes import create_tool_recommendation

        app = Flask(__name__)
        with app.test_request_context("/tool_recommendations", method="POST", json={}):
            g.auth = SimpleNamespace(kind="user", user_id=1)
            with pytest.raises(Exception) as exc_info:
                create_tool_recommendation()

        assert exc_info.value.code == 400

    def test_create_rejects_unknown_status(self):
        from library.tool_recommendation_routes import create_tool_recommendation

        app = Flask(__name__)
        with app.test_request_context("/tool_recommendations", method="POST", json={"name": "LinkStack", "status": "new"}):
            g.auth = SimpleNamespace(kind="user", user_id=1)
            with pytest.raises(Exception) as exc_info:
                create_tool_recommendation()

        assert exc_info.value.code == 400

    def test_status_change_updates_item(self, monkeypatch):
        from library.tool_recommendation_routes import update_status

        session = MagicMock()
        item = _item()
        session.get.return_value = item
        monkeypatch.setattr("library.tool_recommendation_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)

        with app.test_request_context("/tool_recommendations/17/status", method="POST", json={"status": "compare"}):
            g.auth = SimpleNamespace(kind="user", user_id=1)
            response = update_status(17)

        assert item.status == "compare"
        assert response.json["tool_recommendation"]["status"] == "compare"
        session.commit.assert_called_once()

    def test_read_only_key_cannot_change_status(self):
        from library.tool_recommendation_routes import update_status

        app = Flask(__name__)
        with app.test_request_context("/tool_recommendations/17/status", method="POST", json={"status": "compare"}):
            g.auth = SimpleNamespace(kind="service", user_id=None)
            with pytest.raises(Exception) as exc_info:
                update_status(17)

        assert exc_info.value.code == 403
