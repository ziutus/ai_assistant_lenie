from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")

from flask import Flask, g

from library import tool_profile_suggester as profile

CATEGORIES = [("Development", 80), ("AI", 22), ("DataScience", 4), ("DecisionModels", 3)]


def _item(**overrides):
    values = {"id": 11, "name": "JupyterLab", "homepage_url": "https://github.com/jupyterlab/jupyterlab",
              "description": "JupyterLab computational environment.", "category": "AI", "tags": ["notebooks"],
              "links": [{"url": "https://jupyter.org", "label": "Strona"}]}
    values.update(overrides)
    return SimpleNamespace(**values)


ANSWER = ('{"description": "Interaktywne środowisko do notatników.", "category": "data science", '
          '"tags": ["Python", "notebooks", "jupyter"], "confidence": "known"}')


class TestPrompt:
    def test_prompt_carries_facts_categories_tags_and_the_rules(self):
        item = _item()
        github = {"description": "Notebook IDE", "topics": ["jupyter", "ide"]}
        prompt = profile.build_prompt(item.name, item.homepage_url, item.links, item.description, item.category,
                                      item.tags, github, CATEGORIES, ["python", "docker"])

        assert "JupyterLab" in prompt and "https://jupyter.org" in prompt
        assert "GitHub description: Notebook IDE" in prompt and "GitHub topics: jupyter, ide" in prompt
        assert "Development (80), AI (22), DataScience (4), DecisionModels (3)" in prompt
        assert "Tags already used elsewhere on the radar: python, docker" in prompt
        assert "Tags already on this tool: notebooks" in prompt
        assert "IN POLISH" in prompt and "use what you already know" in prompt.lower()
        assert "AI or Tools" in prompt  # broad categories are to be narrowed

    def test_without_github_or_vocabulary(self):
        prompt = profile.build_prompt("X", None, [], None, None, [], None, [], None)
        assert "GitHub" not in prompt and "(none yet)" in prompt and "Homepage: -" in prompt


class TestParseAnswer:
    def test_plain_and_fenced(self):
        assert profile.parse_answer(ANSWER)["category"] == "data science"
        assert profile.parse_answer("```json\n" + ANSWER + "\n```")["confidence"] == "known"

    @pytest.mark.parametrize("raw", [None, "", "no json", '{"description": 1, "category": "A"}', '{"description": "x"}', "{broken"])
    def test_unusable_answers(self, raw):
        assert profile.parse_answer(raw) is None

    def test_unknown_confidence_and_bad_tags_are_tolerated(self):
        parsed = profile.parse_answer('{"description": "x", "category": "A", "tags": "docker", "confidence": "sure"}')
        assert parsed["confidence"] == "partial" and parsed["tags"] == []
        assert profile.parse_answer('{"description": "x", "category": "A", "tags": ["a", 3]}')["tags"] == ["a"]


class TestCleanProfile:
    def _parsed(self, **overrides):
        values = {"description": "  Opis   w dwóch\nwierszach. ", "category": "data science", "tags": ["Python", "notebooks"],
                  "confidence": "known"}
        values.update(overrides)
        return values

    def test_reuses_the_existing_spelling_and_marks_the_change(self):
        result = profile.clean_profile(self._parsed(), "AI", CATEGORIES, ["notebooks"], "JupyterLab")
        assert result["category"] == "DataScience"  # "data science" folds onto the stored spelling
        assert (result["category_is_new"], result["category_changed"]) == (False, True)
        assert result["description"] == "Opis w dwóch wierszach."
        assert result["tags"] == ["python"]  # "notebooks" is already on the tool

    def test_new_category_is_camel_cased_and_flagged(self):
        result = profile.clean_profile(self._parsed(category="note-taking apps"), "AI", CATEGORIES)
        assert result["category"] == "NoteTakingApps" and result["category_is_new"] is True

    def test_repeating_the_current_category_is_no_change(self):
        result = profile.clean_profile(self._parsed(category="ai"), "AI", CATEGORIES)
        assert (result["category"], result["category_changed"], result["category_is_new"]) == ("AI", False, False)

    def test_unknown_tool_gets_no_description_and_no_tags(self):
        result = profile.clean_profile(self._parsed(confidence="unknown"), "AI", CATEGORIES)
        assert result["description"] == "" and result["tags"] == []

    def test_empty_category_is_none(self):
        assert profile.clean_profile(self._parsed(category="  "), "AI", CATEGORIES)["category"] is None

    def test_long_description_is_cut(self):
        result = profile.clean_profile(self._parsed(description="x" * 2000), None, CATEGORIES)
        assert len(result["description"]) == profile.MAX_PROPOSED_DESCRIPTION

    @pytest.mark.parametrize("raw, expected", [
        ("data science", "DataScience"), ("data-science", "DataScience"), ("MediaManagement", "MediaManagement"),
        ("  ai ", "Ai"), ("net/ops!", "NetOps"), ("", ""),
    ])
    def test_normalise_category(self, raw, expected):
        assert profile.normalise_category(raw) == expected


class TestSuggestProfile:
    def _patch_model(self, monkeypatch, answer=None, error=None):
        seen = {}

        def fake_ask(prompt, **kwargs):
            seen.update(prompt=prompt, **kwargs)
            if error:
                raise error
            return SimpleNamespace(response_text=answer, usage=None)

        monkeypatch.setattr("library.ai.ai_ask", fake_ask)
        monkeypatch.setattr(profile, "supports_structured_output", lambda model: False)
        return seen

    def test_one_request_returns_description_category_and_tags(self, monkeypatch):
        seen = self._patch_model(monkeypatch, ANSWER)

        outcome = profile.suggest_profile(_item(), None, CATEGORIES, ["python"], "openrouter/google/gemini-2.5-flash-lite")

        assert outcome["status"] == "ok" and outcome["model"] == "openrouter/google/gemini-2.5-flash-lite"
        assert (outcome["category"], outcome["category_changed"], outcome["confidence"]) == ("DataScience", True, "known")
        assert outcome["tags"] == ["python", "jupyter"] and outcome["description"].startswith("Interaktywne")
        assert outcome["tokens"] is None
        assert seen["operation"] == profile.OPERATION and seen["response_format"] is None and seen["temperature"] == 0.0

    def test_structured_output_is_requested_only_when_supported(self, monkeypatch):
        seen = self._patch_model(monkeypatch, ANSWER)
        monkeypatch.setattr(profile, "supports_structured_output", lambda model: True)
        profile.suggest_profile(_item(), None, CATEGORIES, [], "m")
        schema = seen["response_format"]["json_schema"]["schema"]
        assert set(schema["required"]) == {"description", "category", "tags", "confidence"}

    def test_unparseable_answer_is_an_error_not_an_empty_proposal(self, monkeypatch):
        self._patch_model(monkeypatch, "I cannot help")
        outcome = profile.suggest_profile(_item(), None, CATEGORIES, [], "m")
        assert outcome["status"] == "error" and outcome["error_code"] == "unparseable_answer"

    def test_provider_failure_is_reported(self, monkeypatch):
        self._patch_model(monkeypatch, error=RuntimeError("down"))
        outcome = profile.suggest_profile(_item(), None, CATEGORIES, [], "m")
        assert outcome["status"] == "error" and outcome["error_code"] == "RuntimeError"


class TestRoute:
    def _call(self, monkeypatch, body=None, item="default", kind="user", rows=None):
        from library.tool_recommendation_routes import suggest_profile

        session = MagicMock()
        session.get.return_value = _item() if item == "default" else item
        session.execute.return_value.all.return_value = rows if rows is not None else [("AI", 22), ("Development", 80), (None, 3)]
        session.execute.return_value.scalars.return_value.all.return_value = [["python"], ["python", "docker"], None]
        monkeypatch.setattr("library.tool_recommendation_routes.get_scoped_session", lambda: session)
        monkeypatch.setattr("library.tool_recommendation_routes.github_repo_stats.combined_stats_for_entries", lambda *_a: {})
        monkeypatch.setattr("library.tool_tag_suggester.default_model", lambda _session: "gpt-4o-mini")
        seen = {}

        def fake_suggest(entry, github, categories, vocabulary, model):
            seen.update(categories=categories, vocabulary=vocabulary, model=model)
            return {"status": "ok", "model": model}

        monkeypatch.setattr("library.tool_profile_suggester.suggest_profile", fake_suggest)
        with Flask(__name__).test_request_context("/tool_recommendations/11/suggest_profile", method="POST", json=body or {}):
            g.auth = SimpleNamespace(kind=kind, user_id=1)
            response = suggest_profile(11)
        return response, seen

    def test_passes_categories_vocabulary_and_default_model(self, monkeypatch):
        response, seen = self._call(monkeypatch)
        assert response.json == {"status": "ok", "model": "gpt-4o-mini"}
        assert seen["categories"] == [("AI", 22), ("Development", 80)]  # the row without a label is dropped
        assert seen["vocabulary"] == ["python", "docker"]  # most used first

    def test_a_chosen_allowed_model_wins(self, monkeypatch):
        monkeypatch.setattr("library.llm_model_registry.is_selectable", lambda model, task: True)
        _, seen = self._call(monkeypatch, {"model": "openrouter/google/gemini-2.5-flash-lite"})
        assert seen["model"] == "openrouter/google/gemini-2.5-flash-lite"

    def test_unknown_model_is_a_400(self, monkeypatch):
        monkeypatch.setattr("library.llm_model_registry.is_selectable", lambda model, task: False)
        with pytest.raises(Exception) as exc_info:
            self._call(monkeypatch, {"model": "not-allowed"})
        assert exc_info.value.code == 400

    def test_unknown_entry_is_a_404(self, monkeypatch):
        with pytest.raises(Exception) as exc_info:
            self._call(monkeypatch, item=None)
        assert exc_info.value.code == 404

    def test_other_key_kinds_are_refused(self, monkeypatch):
        with pytest.raises(Exception) as exc_info:
            self._call(monkeypatch, kind="anonymous")
        assert exc_info.value.code == 403
