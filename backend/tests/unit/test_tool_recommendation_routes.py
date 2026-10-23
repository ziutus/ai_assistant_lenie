import datetime as dt
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")

from flask import Flask, g


def _item(status="watchlist"):
    return SimpleNamespace(
        id=17, name="LinkStack", homepage_url="https://github.com/LinkStackOrg/linkstack",
        description="Współdzielona strona z linkami", category="bookmarking", tags=["links"], status=status,
        personal_note=None, obsidian_note_path=None, source_url="https://example.com/awesome", source_context="Awesome Homelab",
        source_document_id=None, source_candidate_id=None, source_document=None, tool_id=None,
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

    def test_peers_match_category_spelling_and_hide_adopted_duplicate(self, monkeypatch):
        from library.tool_recommendation_routes import get_recommendation_peers

        clef = _item()
        clef.id, clef.name, clef.category, clef.tool_id = 730, "Clef", "DecisionModels", None
        basal = _item("adopted")
        basal.id, basal.name, basal.category, basal.tool_id = 732, "Basal", "decision-models", 20
        other = _item()
        other.id, other.name, other.category, other.tool_id = 5, "Redis", "Caching", None
        basal_tool = SimpleNamespace(id=20, name="Basal", homepage_url="https://fabryka.ai", status="accepted",
                                     category_tags=["decision-models"], personal_notes=None, pricing=None, license=None)
        manual_tool = SimpleNamespace(id=21, name="Zapier", homepage_url=None, status="accepted",
                                      category_tags=["Decision Models"], personal_notes="notatka", pricing=None, license=None)
        session = MagicMock()
        session.get.return_value = clef
        session.execute.return_value.scalars.return_value.all.side_effect = [[basal, other], [basal_tool, manual_tool]]
        monkeypatch.setattr("library.tool_recommendation_routes.get_scoped_session", lambda: session)
        monkeypatch.setattr("library.tool_recommendation_routes.github_repo_stats.stats_for_urls", lambda *_args: {})
        app = Flask(__name__)

        with app.test_request_context("/tool_recommendations/730/peers"):
            g.auth = SimpleNamespace(kind="user", user_id=1)
            response = get_recommendation_peers(730)

        assert [entry["name"] for entry in response.json["radar"]] == ["Basal"]
        assert [tool["name"] for tool in response.json["tools"]] == ["Zapier"]

    def test_peers_of_uncategorised_entry_are_empty(self, monkeypatch):
        from library.tool_recommendation_routes import get_recommendation_peers

        item = _item()
        item.category = None
        session = MagicMock()
        session.get.return_value = item
        monkeypatch.setattr("library.tool_recommendation_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)

        with app.test_request_context("/tool_recommendations/17/peers"):
            g.auth = SimpleNamespace(kind="user", user_id=1)
            response = get_recommendation_peers(17)

        assert response.json == {"category": None, "radar": [], "tools": []}

    def test_unsupported_key_kind_forbidden(self):
        from library.tool_recommendation_routes import update_status

        app = Flask(__name__)
        with app.test_request_context("/tool_recommendations/17/status", method="POST", json={"status": "compare"}):
            g.auth = SimpleNamespace(kind="other", user_id=None)
            with pytest.raises(Exception) as exc_info:
                update_status(17)

        assert exc_info.value.code == 403

    def test_service_key_can_change_status(self, monkeypatch):
        from library.tool_recommendation_routes import update_status

        item = _item()
        session = MagicMock()
        session.get.return_value = item
        monkeypatch.setattr("library.tool_recommendation_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)

        with app.test_request_context("/tool_recommendations/17/status", method="POST", json={"status": "compare"}):
            g.auth = SimpleNamespace(kind="service", user_id=None)
            update_status(17)

        assert item.status == "compare"

    def test_patch_sets_and_clears_obsidian_note_path(self, monkeypatch):
        from library.tool_recommendation_routes import update_tool_recommendation

        item = _item()
        session = MagicMock()
        session.get.return_value = item
        monkeypatch.setattr("library.tool_recommendation_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)

        with app.test_request_context(
            "/tool_recommendations/17", method="PATCH", json={"obsidian_note_path": " 02-wiedza/Informatyka/jq.md "},
        ):
            g.auth = SimpleNamespace(kind="service", user_id=None)
            response = update_tool_recommendation(17)

        assert item.obsidian_note_path == "02-wiedza/Informatyka/jq.md"
        assert response.json["tool_recommendation"]["obsidian_note_path"] == "02-wiedza/Informatyka/jq.md"

        with app.test_request_context("/tool_recommendations/17", method="PATCH", json={"obsidian_note_path": ""}):
            g.auth = SimpleNamespace(kind="user", user_id=1)
            update_tool_recommendation(17)

        assert item.obsidian_note_path is None
        assert session.commit.call_count == 2

    def test_patch_leaves_absent_fields_and_rejects_non_strings(self, monkeypatch):
        from library.tool_recommendation_routes import update_tool_recommendation

        item = _item()
        session = MagicMock()
        session.get.return_value = item
        monkeypatch.setattr("library.tool_recommendation_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)

        with app.test_request_context("/tool_recommendations/17", method="PATCH", json={"category": "cli"}):
            g.auth = SimpleNamespace(kind="user", user_id=1)
            update_tool_recommendation(17)
        assert item.category == "cli"
        assert item.description == "Współdzielona strona z linkami"

        with app.test_request_context("/tool_recommendations/17", method="PATCH", json={"category": 5}):
            g.auth = SimpleNamespace(kind="user", user_id=1)
            with pytest.raises(Exception) as exc_info:
                update_tool_recommendation(17)
        assert exc_info.value.code == 400


class TestTags:
    def test_normalize_lowercases_dedupes_and_joins_words(self):
        from library.tool_recommendation_routes import normalize_tags

        assert normalize_tags([" Docker ", "docker", "Container Images", "", "SBOM"]) == [
            "docker", "container-images", "sbom",
        ]
        assert normalize_tags(None) == []

    def test_normalize_rejects_non_list_and_long_tags(self):
        from werkzeug.exceptions import BadRequest

        from library.tool_recommendation_routes import normalize_tags

        with pytest.raises(BadRequest):
            normalize_tags("docker")
        with pytest.raises(BadRequest):
            normalize_tags(["x" * 41])
        with pytest.raises(BadRequest):
            normalize_tags([f"t{i}" for i in range(21)])

    def test_catalog_tags_put_category_first_without_repeats(self):
        from library.tool_recommendation_routes import _catalog_tags

        item = SimpleNamespace(category="security", tags=["docker", "security", "sbom"])
        assert _catalog_tags(item) == ["security", "docker", "sbom"]
        assert _catalog_tags(SimpleNamespace(category=None, tags=None)) == []

    def test_dict_exposes_tags(self):
        from library.tool_recommendation_routes import _dict

        assert _dict(_item())["tags"] == ["links"]
