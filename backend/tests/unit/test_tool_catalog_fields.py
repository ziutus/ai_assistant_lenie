"""Catalog detail fields of a tool: links, pricing type, key points, GitHub numbers and "migrating away"."""

import datetime as dt
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")

from flask import Flask, g


def _make_tool(**overrides):
    defaults = dict(
        id=1, uuid="11111111-1111-1111-1111-111111111111", name="Terraform", category_tags=[],
        homepage_url="https://terraform.io", license=None, pricing=None, personal_notes=None,
        source_document_id=None, source_candidate_id=None, status="accepted", obsidian_note_path=None,
        github_url=None, wikipedia_url=None, pricing_url=None, pricing_type=None, app_type=None,
        key_points=[], important_commands=None, migrating_away=False, migration_note=None,
        migration_target_tool_id=None,
        created_at=dt.datetime(2026, 8, 10, 12, 0, tzinfo=dt.timezone.utc), updated_at=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _patch(monkeypatch, tool, body):
    from library.tool_routes import update_tool

    session = MagicMock()
    session.get.return_value = tool
    session.execute.return_value.scalar_one_or_none.return_value = "OpenTofu"  # name of the migration target
    monkeypatch.setattr("library.tool_routes.get_scoped_session", lambda: session)
    with Flask(__name__).test_request_context("/tools/1", method="PATCH", json=body):
        g.auth = SimpleNamespace(kind="user", user_id=1)
        return update_tool(1), session


class TestPatchDetailFields:
    def test_sets_detail_fields(self, monkeypatch):
        tool = _make_tool()
        response, session = _patch(monkeypatch, tool, {
            "github_url": "https://github.com/hashicorp/terraform",
            "wikipedia_url": "https://en.wikipedia.org/wiki/Terraform_(software)",
            "pricing_url": "https://www.hashicorp.com/pricing", "pricing_type": "open_core", "app_type": " CLI ",
            "key_points": [" deklaratywny ", "", "plan/apply"], "important_commands": "terraform plan\nterraform apply\n",
            "migrating_away": True, "migration_note": "przechodzę na OpenTofu",
        })

        assert tool.github_url == "https://github.com/hashicorp/terraform"
        assert tool.app_type == "CLI" and tool.pricing_type == "open_core"
        assert tool.key_points == ["deklaratywny", "plan/apply"]
        assert tool.important_commands == "terraform plan\nterraform apply\n"
        assert tool.migrating_away is True and tool.migration_note == "przechodzę na OpenTofu"
        assert response.json["tool"]["migrating_away"] is True
        session.commit.assert_called_once()

    def test_empty_values_clear_fields(self, monkeypatch):
        tool = _make_tool(github_url="https://github.com/a/b", migrating_away=True, migration_note="x")
        _patch(monkeypatch, tool, {"github_url": "", "migration_note": "  ", "migrating_away": False})

        assert tool.github_url is None and tool.migration_note is None and tool.migrating_away is False

    def test_sets_and_clears_migration_target(self, monkeypatch):
        tool = _make_tool(migrating_away=True)
        _patch(monkeypatch, tool, {"migration_target_tool_id": 7})
        assert tool.migration_target_tool_id == 7

        _patch(monkeypatch, tool, {"migration_target_tool_id": None})
        assert tool.migration_target_tool_id is None

    def test_turning_migration_off_clears_the_target(self, monkeypatch):
        tool = _make_tool(migrating_away=True, migration_target_tool_id=7)
        _patch(monkeypatch, tool, {"migrating_away": False})
        assert tool.migration_target_tool_id is None

    def test_target_is_ignored_while_not_migrating(self, monkeypatch):
        tool = _make_tool(migrating_away=False)
        _patch(monkeypatch, tool, {"migration_target_tool_id": 7})
        assert tool.migration_target_tool_id is None

    def test_rejects_unknown_target(self, monkeypatch):
        from flask import Flask, g
        from types import SimpleNamespace
        from unittest.mock import MagicMock
        from werkzeug.exceptions import BadRequest

        from library.tool_routes import update_tool

        tool = _make_tool(migrating_away=True)
        session = MagicMock()
        session.get.side_effect = lambda model, key: tool if key == tool.id else None
        monkeypatch.setattr("library.tool_routes.get_scoped_session", lambda: session)
        with Flask(__name__).test_request_context("/tools/1", method="PATCH", json={"migration_target_tool_id": 99}):
            g.auth = SimpleNamespace(kind="user", user_id=1)
            with pytest.raises(BadRequest):
                update_tool(1)

    @pytest.mark.parametrize("body", [
        {"migration_target_tool_id": 1},
        {"migration_target_tool_id": "7"},
        {"migration_target_tool_id": True},
        {"github_url": "https://gitlab.com/a/b"},
        {"github_url": "github.com/a/b"},
        {"wikipedia_url": "javascript:alert(1)"},
        {"pricing_type": "cheap"},
        {"key_points": "jeden"},
        {"key_points": [1, 2]},
        {"migrating_away": "tak"},
        {"important_commands": 5},
    ])
    def test_rejects_bad_values(self, monkeypatch, body):
        from werkzeug.exceptions import BadRequest

        with pytest.raises(BadRequest):
            _patch(monkeypatch, _make_tool(), body)


class TestGithubNumbers:
    def test_get_tools_attaches_stats_by_explicit_link_or_github_homepage(self, monkeypatch):
        from library.tool_routes import get_tools

        explicit = _make_tool(id=1, github_url="https://github.com/hashicorp/terraform")
        by_homepage = _make_tool(id=2, name="Releases", homepage_url="https://github.com/obsidianmd/obsidian-releases")
        plain = _make_tool(id=3, name="Notion")
        session = MagicMock()
        session.execute.return_value.scalars.return_value.all.return_value = [explicit, by_homepage, plain]
        monkeypatch.setattr("library.tool_routes.get_scoped_session", lambda: session)
        monkeypatch.setattr("library.tool_routes.tool_relations_service.relations_for_tools", lambda *_a: {})
        asked = {}

        def fake_stats(_session, urls):
            asked["urls"] = list(urls)
            return {url: {"full_name": url, "stars": 7} for url in urls}

        monkeypatch.setattr("library.tool_routes.github_repo_stats.stats_for_urls", fake_stats)

        with Flask(__name__).test_request_context("/tools"):
            g.auth = SimpleNamespace(kind="user", user_id=1)
            tools = get_tools().json["tools"]

        assert asked["urls"] == ["https://github.com/hashicorp/terraform", "https://github.com/obsidianmd/obsidian-releases"]
        assert [tool["github"] is not None for tool in tools] == [True, True, False]

    def test_refresh_bounds_limit_and_commits(self, monkeypatch):
        from werkzeug.exceptions import BadRequest, Forbidden
        from library.tool_routes import refresh_github_stats

        session = MagicMock()
        session.execute.return_value.scalars.return_value.all.return_value = [_make_tool(github_url="https://github.com/a/b")]
        monkeypatch.setattr("library.tool_routes.get_scoped_session", lambda: session)
        seen = {}
        monkeypatch.setattr(
            "library.tool_routes.github_repo_stats.refresh_stale",
            lambda _s, urls, limit: seen.update(urls=list(urls), limit=limit) or {"refreshed": 1},
        )
        app = Flask(__name__)

        with app.test_request_context("/tools/github_stats/refresh", method="POST", json={"limit": 5}):
            g.auth = SimpleNamespace(kind="user", user_id=1)
            assert refresh_github_stats().json == {"refreshed": 1}
        assert seen == {"urls": ["https://github.com/a/b"], "limit": 5}
        session.commit.assert_called_once()

        with app.test_request_context("/tools/github_stats/refresh", method="POST", json={"limit": 0}):
            g.auth = SimpleNamespace(kind="user", user_id=1)
            with pytest.raises(BadRequest):
                refresh_github_stats()
        with app.test_request_context("/tools/github_stats/refresh", method="POST", json={}):
            g.auth = SimpleNamespace(kind="service", user_id=None)
            with pytest.raises(Forbidden):
                refresh_github_stats()


class TestCreateAndAdopt:
    def test_post_accepts_detail_fields(self, monkeypatch):
        from library.tool_routes import create_tool

        session = MagicMock()
        monkeypatch.setattr("library.tool_routes.get_scoped_session", lambda: session)

        with Flask(__name__).test_request_context("/tools", method="POST", json={
            "name": "Obsidian", "pricing_type": "freemium", "key_points": ["notatki w markdown"], "migrating_away": True,
        }):
            g.auth = SimpleNamespace(kind="user", user_id=1)
            create_tool()

        added = session.add.call_args[0][0]
        assert added.pricing_type == "freemium"
        assert added.key_points == ["notatki w markdown"] and added.migrating_away is True

    def test_adopting_a_github_radar_entry_copies_the_repository_link(self, monkeypatch):
        from library.tool_recommendation_routes import _ensure_tool

        session = MagicMock()
        session.execute.return_value.scalars.return_value.first.return_value = None
        item = SimpleNamespace(
            name="Zed", homepage_url="https://github.com/zed-industries/zed", category="editors",
            personal_note=None, source_document_id=None, source_candidate_id=None,
        )

        tool, created = _ensure_tool(session, item)

        assert created is True and tool.github_url == "https://github.com/zed-industries/zed"
        plain = SimpleNamespace(**{**vars(item), "name": "Notion", "homepage_url": "https://notion.so"})
        assert _ensure_tool(session, plain)[0].github_url is None
