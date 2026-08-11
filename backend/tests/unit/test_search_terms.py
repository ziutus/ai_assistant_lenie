from types import SimpleNamespace

from library import search_terms


def test_generate_search_terms_parses_deduplicates_and_limits(monkeypatch):
    monkeypatch.setattr(
        "library.ai.ai_ask",
        lambda *args, **kwargs: SimpleNamespace(
            response_text="NDA, audyt umowy\n- sprawdzenie NDA, NDA, analiza ryzyka, narzędzie prawne, za dużo",
        ),
    )
    monkeypatch.setattr("library.article_tagging._tagging_model", lambda: "fake-model")

    assert search_terms.generate_search_terms("treść", "tytuł") == [
        "NDA", "audyt umowy", "sprawdzenie NDA", "analiza ryzyka", "narzędzie prawne", "za dużo",
    ]


def test_generate_search_terms_fails_softly(monkeypatch):
    monkeypatch.setattr("library.article_tagging._tagging_model", lambda: "fake-model")
    monkeypatch.setattr("library.ai.ai_ask", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError()))
    assert search_terms.generate_search_terms("treść", "tytuł") == []
