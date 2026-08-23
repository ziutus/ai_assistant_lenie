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
    def test_bulk_status_changes_only_selected_entries(self, monkeypatch):
        from library.tool_recommendation_routes import bulk_update_status

        first, second = _item(), _item()
        first.id, second.id = 11, 12
        session = MagicMock()
        session.execute.return_value.scalars.return_value.all.return_value = [first, second]
        monkeypatch.setattr("library.tool_recommendation_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)

        with app.test_request_context("/tool_recommendations/bulk_status", method="POST", json={"ids": [11, 12], "status": "compare"}):
            g.auth = SimpleNamespace(kind="user", user_id=1)
            response = bulk_update_status()

        assert first.status == second.status == "compare"
        assert response.json == {"updated": 2, "status": "compare", "tools_created": []}
        session.commit.assert_called_once()

    def test_import_returns_names_of_already_present_items(self, monkeypatch):
        from library.tool_recommendation_routes import import_markdown_recommendations

        session = MagicMock()
        first_result = MagicMock()
        first_result.scalar_one_or_none.return_value = SimpleNamespace(id=42, source_document_id=None)
        no_result = MagicMock()
        no_result.scalar_one_or_none.return_value = None
        source_not_found = MagicMock()
        source_not_found.scalars.return_value.first.return_value = None
        session.execute.side_effect = [source_not_found, first_result, no_result, no_result, no_result]
        monkeypatch.setattr("library.tool_recommendation_routes.get_scoped_session", lambda: session)
        monkeypatch.setattr("library.tool_recommendation_routes._existing_tool", lambda *_args: None)
        monkeypatch.setattr("library.tool_recommendation_routes.fetch_markdown", lambda _url: "unused")
        monkeypatch.setattr("library.tool_recommendation_routes.parse_markdown_recommendations", lambda _markdown: [
            {"name": "LinkStack", "homepage_url": "https://example.com/linkstack", "description": None, "category": "Bookmarking"},
            {"name": "Linkding", "homepage_url": "https://example.com/linkding", "description": None, "category": "Bookmarking"},
        ])
        app = Flask(__name__)

        with app.test_request_context("/tool_recommendations/import_markdown", method="POST", json={"source_url": "https://github.com/example/list"}):
            g.auth = SimpleNamespace(kind="user", user_id=1)
            response = import_markdown_recommendations()

        assert response[0].json["skipped_items"] == [{"name": "LinkStack", "existing_id": 42, "reason": "already_in_radar"}]
        assert response[0].json["created"] == 1

    def test_import_attaches_a_lenie_source_document(self, monkeypatch):
        from library.tool_recommendation_routes import import_markdown_recommendations

        session = MagicMock()
        session.get.return_value = SimpleNamespace(id=10333, title="Awesome Homelab", discovery_source=None)
        lookup = MagicMock()
        lookup.scalar_one_or_none.return_value = None
        session.execute.return_value = lookup
        monkeypatch.setattr("library.tool_recommendation_routes.get_scoped_session", lambda: session)
        monkeypatch.setattr("library.tool_recommendation_routes._existing_tool", lambda *_args: None)
        monkeypatch.setattr("library.tool_recommendation_routes.fetch_markdown", lambda _url: "unused")
        monkeypatch.setattr("library.tool_recommendation_routes.parse_markdown_recommendations", lambda _markdown: [
            {"name": "LinkStack", "homepage_url": "https://example.com/linkstack", "description": None, "category": "Bookmarking"},
        ])
        app = Flask(__name__)

        with app.test_request_context("/tool_recommendations/import_markdown", method="POST", json={"source_url": "https://github.com/example/list", "source_document_id": 10333}):
            g.auth = SimpleNamespace(kind="user", user_id=1)
            response = import_markdown_recommendations()

        assert response[0].json["created"] == 1
        assert session.add.call_args_list[0][0][0].source_document_id == 10333

    def test_import_resolves_catalog_url_to_existing_lenie_document(self, monkeypatch):
        from library.tool_recommendation_routes import _resolve_source_document

        document = SimpleNamespace(id=10333)
        session = MagicMock()
        session.execute.return_value.scalars.return_value.first.return_value = document

        assert _resolve_source_document(session, "https://github.com/AwesomeHomelab/awesome-homelab", None) is document

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
