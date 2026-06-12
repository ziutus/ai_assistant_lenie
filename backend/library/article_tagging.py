"""Tagowanie artykułów przez LLM: klasyfikacja tematyczna i ekstrakcja krajów.

Model LLM jest konfigurowalny przez zmienną TAGGING_MODEL (config_loader),
domyślnie Bielik. Wydzielone z imports/article_browser.py, aby można było
tagować także w pipeline'ach batch.
"""

import re

DEFAULT_TAGGING_MODEL = "Bielik-11B-v3.0-Instruct"

THEMATIC_TAGS = [
    "wojsko", "gospodarka", "geopolityka", "ideologia",
    "religia", "demografia", "etniczne", "soft-power-religijny",
    "ustroj", "sluzby-specjalne", "technologia", "internet",
    "finanse-publiczne", "sojusze",
]

# Tagi tematyczne, które wyzwalają automatyczną ekstrakcję krajów
COUNTRY_TAG_TRIGGERS = {"geopolityka", "wojsko", "sojusze", "sluzby-specjalne", "finanse-publiczne", "gospodarka"}


def _tagging_model() -> str:
    """Model LLM do tagowania — z configa (TAGGING_MODEL) lub domyślny Bielik."""
    from library.config_loader import load_config
    return load_config().get("TAGGING_MODEL") or DEFAULT_TAGGING_MODEL


def tag_article_with_llm(text: str, title: str) -> list[str]:
    """Klasyfikuj artykuł według kategorii tematycznych. Zwraca listę tagów."""
    from library.ai import ai_ask

    tags_list = ", ".join(THEMATIC_TAGS)
    prompt = (
        f"Przeczytaj poniższy artykuł i wybierz kategorie tematyczne, które są w nim WYRAŹNIE omawiane.\n\n"
        f"Dostępne kategorie: {tags_list}\n\n"
        f"Zwróć TYLKO listę wybranych kategorii oddzielonych przecinkami, bez żadnych wyjaśnień.\n"
        f"Jeśli żadna kategoria nie pasuje, zwróć pustą odpowiedź.\n\n"
        f"TYTUŁ: {title}\n\nTREŚĆ:\n{text[:3000]}"
    )
    try:
        response = ai_ask(prompt, model=_tagging_model(), temperature=0.0, max_token_count=100)
        raw = response.response_text.strip().lower()
        found = [t.strip() for t in raw.split(",") if t.strip() in THEMATIC_TAGS]
        return found
    except Exception as e:
        print(f"  OSTRZEŻENIE: klasyfikacja tematyczna nie powiodła się: {e}")
        return []


def extract_countries_with_llm(text: str, title: str) -> list[str]:
    """Wyciągnij nazwy krajów z artykułu. Zwraca listę tagów w formacie 'kraj-nazwa'."""
    from library.ai import ai_ask

    prompt = (
        f"Przeczytaj poniższy artykuł i wymień kraje, które są w nim WYRAŹNIE omawiane.\n\n"
        f"Zwróć TYLKO listę nazw krajów oddzielonych przecinkami, małymi literami, po polsku, bez wyjaśnień.\n"
        f"Nazwy wielowyrazowe zapisuj z myślnikiem (np. korea-polnocna, arabia-saudyjska).\n"
        f"Jeśli żaden kraj nie jest wyraźnie omawiany, zwróć pustą odpowiedź.\n\n"
        f"TYTUŁ: {title}\n\nTREŚĆ:\n{text[:3000]}"
    )
    try:
        response = ai_ask(prompt, model=_tagging_model(), temperature=0.0, max_token_count=150)
        raw = response.response_text.strip().lower()
        if not raw:
            return []
        countries = []
        for item in raw.split(","):
            name = item.strip().replace(" ", "-")
            if name and re.match(r'^[a-zà-žąćęłńóśźż-]+$', name):
                countries.append(f"kraj-{name}")
        return countries
    except Exception as e:
        print(f"  OSTRZEŻENIE: ekstrakcja krajów nie powiodła się: {e}")
        return []
