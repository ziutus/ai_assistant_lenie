from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")

from flask import Flask, g

from library import tool_tag_suggester as suggester


def _item(**overrides):
    values = {"id": 779, "name": "Syft", "homepage_url": "https://github.com/anchore/syft",
              "description": "CLI that generates an SBOM from container images", "category": "security",
              "tags": ["security"]}
    values.update(overrides)
    return SimpleNamespace(**values)


class TestParseAnswer:
    def test_plain_json(self):
        assert suggester.parse_answer('{"tags": ["docker", "sbom"]}') == ["docker", "sbom"]

    def test_fenced_and_surrounded_by_prose(self):
        raw = 'Sure!\n```json\n{"tags": ["kubernetes"]}\n```'
        assert suggester.parse_answer(raw) == ["kubernetes"]

    @pytest.mark.parametrize("raw", [None, "", "no json here", '{"tags": "docker"}', '{"other": []}', "{broken"])
    def test_unusable_answers(self, raw):
        assert suggester.parse_answer(raw) is None

    def test_non_string_entries_are_dropped(self):
        assert suggester.parse_answer('{"tags": ["docker", 3, null]}') == ["docker"]


class TestCleanSuggestions:
    def test_normalises_and_drops_repeats_existing_and_own_name(self):
        raw = ["Docker", "docker", "Container Images", "security", "Syft", "  ", "sbom!", "x" * 50]
        assert suggester.clean_suggestions(raw, ["security"], "Syft") == ["docker", "container-images", "sbom"]

    def test_caps_the_count(self):
        raw = [f"tag{i}" for i in range(20)]
        assert len(suggester.clean_suggestions(raw, [], "Tool")) == suggester.MAX_SUGGESTIONS


class TestPrompt:
    def test_prompt_carries_the_entry_and_the_vocabulary(self):
        item = _item()
        prompt = suggester.build_prompt(item.name, item.homepage_url, item.description, item.category,
                                        item.tags, ["docker", "kubernetes"])
        assert "Syft" in prompt and "SBOM" in prompt
        assert "docker, kubernetes" in prompt
        assert "Tags already on this tool: security" in prompt


class TestSuggestTags:
    def _patch_model(self, monkeypatch, answer=None, error=None):
        def fake_ask(prompt, **kwargs):
            if error:
                raise error
            return SimpleNamespace(response_text=answer, usage=None)

        monkeypatch.setattr("library.ai.ai_ask", fake_ask)
        monkeypatch.setattr(suggester, "supports_structured_output", lambda model: False)

    def test_ok(self, monkeypatch):
        self._patch_model(monkeypatch, '{"tags": ["Docker", "sbom", "security"]}')
        outcome = suggester.suggest_tags(_item(), ["docker"], "gpt-4o-mini")
        assert outcome["status"] == "ok"
        assert outcome["tags"] == ["docker", "sbom"]
        assert outcome["model"] == "gpt-4o-mini"
        assert outcome["tokens"] is None  # unknown usage stays None, never 0

    def test_unparseable_answer_is_an_error_not_an_empty_result(self, monkeypatch):
        self._patch_model(monkeypatch, "I cannot help")
        outcome = suggester.suggest_tags(_item(), [], "gpt-4o-mini")
        assert outcome["status"] == "error" and outcome["error_code"] == "unparseable_answer"

    def test_provider_failure_is_reported(self, monkeypatch):
        self._patch_model(monkeypatch, error=RuntimeError("down"))
        outcome = suggester.suggest_tags(_item(), [], "gpt-4o-mini")
        assert outcome["status"] == "error" and outcome["error_code"] == "RuntimeError"


class TestDefaultModel:
    MODELS = [{"id": "Bielik-11B-v3.0-Instruct"}, {"id": "gpt-4o-mini"}, {"id": "gemini-2.0-flash-lite-001"}]

    def _setup(self, monkeypatch, saved, models=None):
        monkeypatch.setattr("library.app_settings.get_setting", lambda session, key, default=None: saved)
        listed = models or self.MODELS
        monkeypatch.setattr("library.llm_model_registry.selectable_models", lambda task="x": listed)
        monkeypatch.setattr("library.llm_model_registry.is_selectable",
                            lambda model, task="x": any(item["id"] == model for item in listed))

    def test_saved_choice_wins_when_allowed(self, monkeypatch):
        self._setup(monkeypatch, "gemini-2.0-flash-lite-001")
        assert suggester.default_model(MagicMock()) == "gemini-2.0-flash-lite-001"

    def test_stale_choice_falls_back_to_gpt_4o_mini_not_bielik(self, monkeypatch):
        self._setup(monkeypatch, "removed-model")
        assert suggester.default_model(MagicMock()) == "gpt-4o-mini"

    def test_without_gpt_the_first_non_bielik_model(self, monkeypatch):
        self._setup(monkeypatch, None, [{"id": "Bielik-11B-v3.0-Instruct"}, {"id": "gemini-2.0-flash-lite-001"}])
        assert suggester.default_model(MagicMock()) == "gemini-2.0-flash-lite-001"

    def test_only_bielik_is_still_better_than_nothing(self, monkeypatch):
        self._setup(monkeypatch, None, [{"id": "Bielik-11B-v3.0-Instruct"}])
        assert suggester.default_model(MagicMock()) == "Bielik-11B-v3.0-Instruct"


class TestRoutes:
    def _app(self):
        app = Flask(__name__)
        return app

    def _auth(self, kind="user"):
        g.auth = SimpleNamespace(kind=kind, user_id=1)

    def test_put_rejects_unknown_model(self, monkeypatch):
        from werkzeug.exceptions import BadRequest

        from library.tool_recommendation_routes import put_tag_model

        monkeypatch.setattr("library.tool_recommendation_routes.get_scoped_session", lambda: MagicMock())
        monkeypatch.setattr("library.llm_model_registry.is_selectable", lambda model, task="x": False)
        with self._app().test_request_context("/tool_recommendations/tag_model", method="PUT", json={"model": "evil"}):
            self._auth()
            with pytest.raises(BadRequest):
                put_tag_model()

    def test_put_saves_and_null_clears(self, monkeypatch):
        from library.tool_recommendation_routes import put_tag_model

        saved = []
        monkeypatch.setattr("library.tool_recommendation_routes.get_scoped_session", lambda: MagicMock())
        monkeypatch.setattr("library.llm_model_registry.is_selectable", lambda model, task="x": True)
        monkeypatch.setattr("library.app_settings.set_setting", lambda session, key, value: saved.append((key, value)))
        monkeypatch.setattr(suggester, "default_model", lambda session: "gpt-4o-mini")
        for value in ("gpt-4o-mini", None):
            with self._app().test_request_context("/tool_recommendations/tag_model", method="PUT", json={"model": value}):
                self._auth()
                response = put_tag_model()
                assert response.get_json()["saved"] is (value is not None)
        assert saved == [("tool_tags_model", "gpt-4o-mini"), ("tool_tags_model", None)]

    def test_suggest_requires_known_entry(self, monkeypatch):
        from werkzeug.exceptions import NotFound

        from library.tool_recommendation_routes import suggest_tags

        session = MagicMock()
        session.get.return_value = None
        monkeypatch.setattr("library.tool_recommendation_routes.get_scoped_session", lambda: session)
        with self._app().test_request_context("/tool_recommendations/1/suggest_tags", method="POST", json={}):
            self._auth()
            with pytest.raises(NotFound):
                suggest_tags(1)
