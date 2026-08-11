"""LLM-generated search phrases kept separate from thematic document tags."""

from __future__ import annotations

import re


MAX_TERMS = 6
MAX_TERM_LENGTH = 80


def generate_search_terms(text: str, title: str) -> list[str]:
    """Return a compact set of likely future search phrases.

    These are retrieval aliases (including synonyms and user intent), not a
    taxonomy.  They are deliberately stored separately from ``Document.tags``.
    """
    from library.article_tagging import _tagging_model
    from library.ai import ai_ask

    prompt = (
        "Na podstawie tytułu i treści podaj 3-6 krótkich fraz, po których użytkownik "
        "mógłby później chcieć znaleźć ten dokument. Uwzględnij nazwane pojęcia, "
        "synonimy i cel użytkownika, ale nie wymyślaj faktów. Jeżeli tekst opisuje "
        "narzędzie lub usługę, PIERWSZA fraza musi opisywać intencję użytkownika "
        "(np. „sprawdzenie umowy”, „analiza dokumentu”), a nie tylko nazwę narzędzia.\n"
        "Zwróć wyłącznie frazy oddzielone przecinkami, bez numeracji i wyjaśnień.\n\n"
        f"TYTUŁ: {title}\n\nTREŚĆ:\n{text[:5000]}"
    )
    try:
        response = ai_ask(
            prompt, model=_tagging_model(), temperature=0.0, max_token_count=160,
            operation="search_terms_generation",
        )
    except Exception:
        return []

    terms: list[str] = []
    seen: set[str] = set()
    for value in re.split(r"[,\n;]", response.response_text):
        term = re.sub(r"^[-*•\d.()\s]+", "", value).strip().strip('"')
        normalized = term.casefold()
        if not term or len(term) > MAX_TERM_LENGTH or normalized in seen:
            continue
        seen.add(normalized)
        terms.append(term)
        if len(terms) == MAX_TERMS:
            break
    return terms
