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
        source_document_id=None, source_candidate_id=None, source_document=None, tool_id=None, links=[],
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
        monkeypatch.setattr("library.tool_recommendation_routes.github_repo_stats.combined_stats_for_entries", lambda *_args: {})
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


class TestEntryUrls:
    def _aisle(self):
        item = _item()
        item.id, item.name, item.homepage_url, item.source_url = 712, "Aisle", None, "gmail://abc"
        item.description = "research Aisle (https://aisle.com/blog/the-model-fixes-code): 30 dolarów, https://aisle.com/blog/the-model-fixes-code."
        return item

    def test_urls_lists_links_once_and_marks_known_documents(self, monkeypatch):
        from library.tool_recommendation_routes import get_recommendation_urls

        known = SimpleNamespace(id=9, title="Znany", document_type="link")
        session = MagicMock()
        session.get.return_value = self._aisle()
        monkeypatch.setattr("library.tool_recommendation_routes.get_scoped_session", lambda: session)
        monkeypatch.setattr("library.tool_recommendation_routes.Document.get_by_url",
                            lambda _s, url: known if url.startswith("https://aisle.com/") else None)
        with Flask(__name__).test_request_context("/tool_recommendations/712/urls"):
            g.auth = SimpleNamespace(kind="user", user_id=1)
            urls = get_recommendation_urls(712).json["urls"]

        assert [u["url"] for u in urls] == ["https://aisle.com/blog/the-model-fixes-code"]
        assert urls[0]["origin"] == "description" and urls[0]["document"]["id"] == 9

    def test_import_url_creates_link_document_and_rejects_foreign_url(self, monkeypatch):
        from library.tool_recommendation_routes import import_recommendation_url

        session = MagicMock()
        session.get.return_value = self._aisle()
        monkeypatch.setattr("library.tool_recommendation_routes.get_scoped_session", lambda: session)
        created = SimpleNamespace(id=55)
        monkeypatch.setattr("library.document_service.DocumentService.import_document",
                            lambda self, url, kind, **meta: (created, "added"))
        app = Flask(__name__)
        with app.test_request_context("/x", method="POST", json={"url": "https://aisle.com/blog/the-model-fixes-code"}):
            g.auth = SimpleNamespace(kind="user", user_id=1)
            response, status = import_recommendation_url(712)
        assert status == 201 and response.json == {"document_id": 55, "created": True}

        with app.test_request_context("/x", method="POST", json={"url": "https://evil.example/x"}):
            g.auth = SimpleNamespace(kind="user", user_id=1)
            with pytest.raises(Exception) as exc_info:
                import_recommendation_url(712)
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


class TestLinks:
    def _patch(self, monkeypatch, body, item=None):
        from library.tool_recommendation_routes import update_tool_recommendation

        item = item or _item()
        session = MagicMock()
        session.get.return_value = item
        monkeypatch.setattr("library.tool_recommendation_routes.get_scoped_session", lambda: session)
        with Flask(__name__).test_request_context("/tool_recommendations/17", method="PATCH", json=body):
            g.auth = SimpleNamespace(kind="user", user_id=1)
            response = update_tool_recommendation(17)
        return item, response, session

    def test_dict_exposes_links(self):
        from library.tool_recommendation_routes import _dict

        item = _item()
        item.links = [{"url": "https://example.com/pricing", "label": "Cennik"}]
        assert _dict(item)["links"] == [{"url": "https://example.com/pricing", "label": "Cennik"}]
        item.links = None
        assert _dict(item)["links"] == []

    def test_patch_replaces_the_whole_list_and_cleans_it(self, monkeypatch):
        item, response, session = self._patch(monkeypatch, {"links": [
            {"url": " https://tt-rss.org ", "label": " Strona "}, "https://github.com/tt-rss/tt-rss",
            {"url": "https://tt-rss.org"},
        ]})

        assert item.links == [
            {"url": "https://tt-rss.org", "label": "Strona"}, {"url": "https://github.com/tt-rss/tt-rss", "label": ""},
        ]
        assert response.json["tool_recommendation"]["links"] == item.links
        session.commit.assert_called_once()

    def test_patch_without_links_leaves_them(self, monkeypatch):
        item = _item()
        item.links = [{"url": "https://example.com", "label": ""}]
        self._patch(monkeypatch, {"category": "cli"}, item)
        assert item.links == [{"url": "https://example.com", "label": ""}]

    def test_patch_empty_list_clears(self, monkeypatch):
        item = _item()
        item.links = [{"url": "https://example.com", "label": ""}]
        self._patch(monkeypatch, {"links": []}, item)
        assert item.links == []

    @pytest.mark.parametrize("links", [
        "https://example.com", [{"url": "javascript:alert(1)"}], [{"url": ""}], [5], [{"url": "https://a.b", "label": 3}],
        [{"url": f"https://example.com/{i}"} for i in range(21)],
    ])
    def test_patch_rejects_bad_links(self, monkeypatch, links):
        with pytest.raises(Exception) as exc_info:
            self._patch(monkeypatch, {"links": links})
        assert exc_info.value.code == 400

    def test_create_accepts_links(self, monkeypatch):
        from library.tool_recommendation_routes import create_tool_recommendation

        session = MagicMock()
        session.execute.return_value.scalars.return_value.first.return_value = None
        monkeypatch.setattr("library.tool_recommendation_routes.get_scoped_session", lambda: session)
        monkeypatch.setattr("library.tool_recommendation_routes.tool_relations_service.detect_relations", lambda *_a: None)
        with Flask(__name__).test_request_context("/tool_recommendations", method="POST", json={
            "name": "Tiny Tiny RSS", "homepage_url": "https://github.com/tt-rss/tt-rss",
            "links": [{"url": "https://gitlab.tt-rss.org/tt-rss/tt-rss", "label": "GitLab"}],
        }):
            g.auth = SimpleNamespace(kind="user", user_id=1)
            create_tool_recommendation()

        created = session.add.call_args[0][0]
        assert created.links == [{"url": "https://gitlab.tt-rss.org/tt-rss/tt-rss", "label": "GitLab"}]

    def test_adoption_copies_links_to_the_catalog_tool(self):
        from library.tool_recommendation_routes import _ensure_tool

        session = MagicMock()
        session.execute.return_value.scalars.return_value.first.return_value = None
        item = _item("adopted")
        item.links = [{"url": "https://example.com/pricing", "label": "Cennik"}]

        tool, created = _ensure_tool(session, item)

        assert created is True
        assert tool.links == [{"url": "https://example.com/pricing", "label": "Cennik"}]

    def test_refresh_of_one_entry_uses_every_repository_link(self, monkeypatch):
        from library.tool_recommendation_routes import refresh_github_stats

        item = _item()
        item.homepage_url = "https://tt-rss.org"
        item.links = [{"url": "https://github.com/tt-rss/tt-rss", "label": ""}, {"url": "https://gitlab.com/tt/mirror", "label": ""}]
        session = MagicMock()
        session.get.return_value = item
        monkeypatch.setattr("library.tool_recommendation_routes.get_scoped_session", lambda: session)
        seen = {}

        def fake_refresh(_session, urls, limit, force=False):
            seen.update(urls=list(urls), limit=limit, force=force)
            return {"refreshed": 2}

        monkeypatch.setattr("library.tool_recommendation_routes.github_repo_stats.refresh_stale", fake_refresh)
        with Flask(__name__).test_request_context("/x", method="POST", json={"id": 17, "force": True}):
            g.auth = SimpleNamespace(kind="user", user_id=1)
            assert refresh_github_stats().json == {"refreshed": 2}

        assert seen == {
            "urls": ["https://tt-rss.org", "https://github.com/tt-rss/tt-rss", "https://gitlab.com/tt/mirror"],
            "limit": 2, "force": True,
        }

    def test_entry_without_any_repository_is_a_400(self, monkeypatch):
        from library.tool_recommendation_routes import refresh_github_stats

        item = _item()
        item.homepage_url = "https://example.com"
        session = MagicMock()
        session.get.return_value = item
        monkeypatch.setattr("library.tool_recommendation_routes.get_scoped_session", lambda: session)
        with Flask(__name__).test_request_context("/x", method="POST", json={"id": 17}):
            g.auth = SimpleNamespace(kind="user", user_id=1)
            with pytest.raises(Exception) as exc_info:
                refresh_github_stats()
        assert exc_info.value.code == 400


class TestToolLinksModule:
    def test_merge_links_adds_new_urls_and_caps(self):
        from library import tool_links, tool_note_parser

        merged = tool_links.merge_links([{"url": "https://a.com", "label": "A"}], [{"url": "https://a.com"}, {"url": "https://b.com", "label": "B"}])
        assert merged == [{"url": "https://a.com", "label": "A"}, {"url": "https://b.com", "label": "B"}]
        many = tool_links.merge_links([], [{"url": f"https://x.com/{i}"} for i in range(tool_note_parser.MAX_LINKS + 5)])
        assert len(many) == tool_note_parser.MAX_LINKS
        assert tool_links.merge_links(None, None) == []
