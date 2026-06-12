"""Unit tests for library.article_tagging — LLM thematic tagging and country extraction.

ai_ask is monkeypatched — no real LLM calls.
"""

from types import SimpleNamespace

import pytest

from library import article_tagging


def _fake_ai(response_text, calls=None):
    """Zwraca podróbkę ai_ask, opcjonalnie rejestrującą wywołania w `calls`."""
    def fake(prompt, model, temperature=0.7, max_token_count=4096, top_p=0.9):
        if calls is not None:
            calls.append({"prompt": prompt, "model": model})
        return SimpleNamespace(response_text=response_text)
    return fake


@pytest.fixture
def fixed_model(monkeypatch):
    """Nie czytaj configa w testach — stały model."""
    monkeypatch.setattr(article_tagging, "_tagging_model", lambda: "fake-model")


@pytest.mark.usefixtures("fixed_model")
class TestTagArticle:
    def test_keeps_only_known_thematic_tags(self, monkeypatch):
        monkeypatch.setattr("library.ai.ai_ask", _fake_ai("Geopolityka, wojsko, kosmici"))
        tags = article_tagging.tag_article_with_llm("treść artykułu", "tytuł")
        assert tags == ["geopolityka", "wojsko"]

    def test_empty_response_returns_empty_list(self, monkeypatch):
        monkeypatch.setattr("library.ai.ai_ask", _fake_ai(""))
        assert article_tagging.tag_article_with_llm("treść", "tytuł") == []

    def test_llm_error_returns_empty_list(self, monkeypatch):
        def boom(*args, **kwargs):
            raise RuntimeError("API down")
        monkeypatch.setattr("library.ai.ai_ask", boom)
        assert article_tagging.tag_article_with_llm("treść", "tytuł") == []

    def test_uses_configured_model(self, monkeypatch):
        calls = []
        monkeypatch.setattr("library.ai.ai_ask", _fake_ai("wojsko", calls))
        article_tagging.tag_article_with_llm("treść", "tytuł")
        assert calls[0]["model"] == "fake-model"

    def test_text_truncated_in_prompt(self, monkeypatch):
        calls = []
        monkeypatch.setattr("library.ai.ai_ask", _fake_ai("", calls))
        article_tagging.tag_article_with_llm("x" * 10000, "tytuł")
        # Do promptu trafia maksymalnie 3000 znaków treści
        assert "x" * 3001 not in calls[0]["prompt"]


@pytest.mark.usefixtures("fixed_model")
class TestExtractCountries:
    def test_countries_get_kraj_prefix(self, monkeypatch):
        monkeypatch.setattr("library.ai.ai_ask", _fake_ai("polska, korea północna"))
        countries = article_tagging.extract_countries_with_llm("treść", "tytuł")
        assert countries == ["kraj-polska", "kraj-korea-północna"]

    def test_invalid_items_filtered_out(self, monkeypatch):
        monkeypatch.setattr("library.ai.ai_ask", _fake_ai("polska, usa123, , !@#"))
        countries = article_tagging.extract_countries_with_llm("treść", "tytuł")
        assert countries == ["kraj-polska"]

    def test_empty_response_returns_empty_list(self, monkeypatch):
        monkeypatch.setattr("library.ai.ai_ask", _fake_ai("   "))
        assert article_tagging.extract_countries_with_llm("treść", "tytuł") == []

    def test_llm_error_returns_empty_list(self, monkeypatch):
        def boom(*args, **kwargs):
            raise RuntimeError("API down")
        monkeypatch.setattr("library.ai.ai_ask", boom)
        assert article_tagging.extract_countries_with_llm("treść", "tytuł") == []


class TestConstants:
    def test_country_triggers_are_subset_of_thematic_tags(self):
        assert article_tagging.COUNTRY_TAG_TRIGGERS <= set(article_tagging.THEMATIC_TAGS)

    def test_default_model_used_when_config_empty(self, monkeypatch):
        pytest.importorskip("unified_config_loader")
        monkeypatch.setattr("library.config_loader.load_config", lambda: {})
        assert article_tagging._tagging_model() == article_tagging.DEFAULT_TAGGING_MODEL

    def test_model_read_from_config(self, monkeypatch):
        pytest.importorskip("unified_config_loader")
        monkeypatch.setattr("library.config_loader.load_config", lambda: {"TAGGING_MODEL": "gpt-4o-mini"})
        assert article_tagging._tagging_model() == "gpt-4o-mini"
