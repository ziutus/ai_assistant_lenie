"""Given-name countries require LLM confirmation even above the mention threshold."""

from types import SimpleNamespace

import pytest

from library import article_tagging
from library.country_gazetteer import canonical_country_name


@pytest.fixture
def fixed_model(monkeypatch):
    monkeypatch.setattr(article_tagging, "_tagging_model", lambda: "fake-model")


@pytest.mark.usefixtures("fixed_model")
@pytest.mark.parametrize("response_text, expected_decision", [("", "llm_rejected"), ("Kuba", "llm_confirmed")])
def test_kuba_requires_llm_confirmation(monkeypatch, response_text, expected_decision):
    calls = []

    def fake(prompt, model, temperature=0.7, max_token_count=4096, top_p=0.9, **kwargs):
        calls.append({"prompt": prompt, "model": model})
        return SimpleNamespace(response_text=response_text)

    monkeypatch.setattr("library.ai.ai_ask", fake)
    audit = {}
    tags = article_tagging.extract_countries_hybrid("Wyspa Kuba jest piekna. " * 6, "", audit)

    assert ("kraj-kuba" in tags) == bool(response_text)
    assert len(calls) == 1
    assert calls[0]["model"] == "fake-model"
    decision = next(d for d in audit["decisions"] if d["name_pl"] == "Kuba")
    assert decision["mention_count"] == 6
    assert decision["decision"] == expected_decision


@pytest.mark.usefixtures("fixed_model")
def test_polska_still_auto_confirmed(monkeypatch):
    def fail_if_called(*args, **kwargs):
        pytest.fail("An auto-confirmed country must not call the LLM")

    monkeypatch.setattr("library.ai.ai_ask", fail_if_called)
    audit = {}
    tags = article_tagging.extract_countries_hybrid("Polska. " * 6, "", audit)

    assert "kraj-polska" in tags
    assert audit["llm"]["called"] is False
    decision = next(d for d in audit["decisions"] if d["name_pl"] == "Polska")
    assert decision["decision"] == "auto_threshold"


def test_confirmation_countries_have_canonical_names():
    assert "Kuba" in article_tagging.COUNTRIES_REQUIRING_CONFIRMATION
    for name in article_tagging.COUNTRIES_REQUIRING_CONFIRMATION:
        assert canonical_country_name(name) == name
