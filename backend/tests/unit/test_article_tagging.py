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
class TestConfirmPlaces:
    def test_returns_subset_matching_candidates(self, monkeypatch):
        monkeypatch.setattr("library.ai.ai_ask", _fake_ai("Cieśnina Ormuz, Wyspa Spoza Listy"))
        result = article_tagging.confirm_places_with_llm(
            "treść", "tytuł", ["Cieśnina Ormuz", "Kijów"])
        assert result == ["Cieśnina Ormuz"]

    def test_case_insensitive_matching(self, monkeypatch):
        monkeypatch.setattr("library.ai.ai_ask", _fake_ai("kijów"))
        assert article_tagging.confirm_places_with_llm("treść", "tytuł", ["Kijów"]) == ["Kijów"]

    def test_empty_candidates_skip_llm(self, monkeypatch):
        calls = []
        monkeypatch.setattr("library.ai.ai_ask", _fake_ai("", calls))
        assert article_tagging.confirm_places_with_llm("treść", "tytuł", []) == []
        assert calls == []

    def test_llm_error_returns_empty_list(self, monkeypatch):
        def boom(*args, **kwargs):
            raise RuntimeError("API down")
        monkeypatch.setattr("library.ai.ai_ask", boom)
        assert article_tagging.confirm_places_with_llm("treść", "tytuł", ["Kijów"]) == []


@pytest.mark.usefixtures("fixed_model")
class TestConfirmPerson:
    CANDIDATES = [
        {"qid": "Q946", "label": "Donald Tusk", "description": "polski polityk"},
        {"qid": "Q17278182", "label": "Donald Tusk", "description": "ojciec Donalda Tuska"},
    ]

    def test_returns_selected_qid(self, monkeypatch):
        monkeypatch.setattr("library.ai.ai_ask", _fake_ai("Q946"))
        assert article_tagging.confirm_person_with_llm("treść", "tytuł", "Tusk", self.CANDIDATES) == "Q946"

    def test_none_response_returns_none(self, monkeypatch):
        monkeypatch.setattr("library.ai.ai_ask", _fake_ai("NONE"))
        assert article_tagging.confirm_person_with_llm("treść", "tytuł", "Tusk", self.CANDIDATES) is None

    def test_qid_outside_candidates_rejected(self, monkeypatch):
        monkeypatch.setattr("library.ai.ai_ask", _fake_ai("Q12345"))
        assert article_tagging.confirm_person_with_llm("treść", "tytuł", "Tusk", self.CANDIDATES) is None

    def test_empty_candidates_skip_llm(self, monkeypatch):
        calls = []
        monkeypatch.setattr("library.ai.ai_ask", _fake_ai("", calls))
        assert article_tagging.confirm_person_with_llm("treść", "tytuł", "Tusk", []) is None
        assert calls == []

    def test_llm_error_returns_none(self, monkeypatch):
        def boom(*args, **kwargs):
            raise RuntimeError("API down")
        monkeypatch.setattr("library.ai.ai_ask", boom)
        assert article_tagging.confirm_person_with_llm("treść", "tytuł", "Tusk", self.CANDIDATES) is None


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


@pytest.mark.usefixtures("fixed_model")
class TestExtractCountriesHybrid:
    def test_no_candidates_skips_llm_call(self, monkeypatch):
        pytest.importorskip("unidecode")
        calls = []
        monkeypatch.setattr("library.ai.ai_ask", _fake_ai("polska", calls))
        result = article_tagging.extract_countries_hybrid("tekst bez żadnego kraju", "tytuł")
        assert result == []
        assert calls == []

    def test_llm_confirms_subset_of_candidates(self, monkeypatch):
        pytest.importorskip("unidecode")
        monkeypatch.setattr("library.ai.ai_ask", _fake_ai("Polska"))
        result = article_tagging.extract_countries_hybrid(
            "Polska i Niemcy podpisały umowę, ale artykuł skupia się na Polsce.", "tytuł"
        )
        assert result == ["kraj-polska"]

    def test_llm_response_outside_candidates_is_ignored(self, monkeypatch):
        pytest.importorskip("unidecode")
        monkeypatch.setattr("library.ai.ai_ask", _fake_ai("Hiszpania"))
        result = article_tagging.extract_countries_hybrid("Polska ogłosiła nowy program.", "tytuł")
        assert result == []

    def test_empty_llm_response_returns_empty_list(self, monkeypatch):
        pytest.importorskip("unidecode")
        monkeypatch.setattr("library.ai.ai_ask", _fake_ai(""))
        result = article_tagging.extract_countries_hybrid("Polska ogłosiła nowy program.", "tytuł")
        assert result == []

    def test_llm_error_returns_empty_list(self, monkeypatch):
        pytest.importorskip("unidecode")

        def boom(*args, **kwargs):
            raise RuntimeError("API down")

        monkeypatch.setattr("library.ai.ai_ask", boom)
        result = article_tagging.extract_countries_hybrid("Polska ogłosiła nowy program.", "tytuł")
        assert result == []


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
