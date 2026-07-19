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
        response = ai_ask(prompt, model=_tagging_model(), temperature=0.0, max_token_count=100,
                          operation="thematic_tagging")
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
        response = ai_ask(prompt, model=_tagging_model(), temperature=0.0, max_token_count=150,
                          operation="country_tagging")
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


def _mention_snippets(text: str, mention: str, window: int = 200, max_snippets: int = 2) -> str:
    """Fragmenty tekstu wokół wystąpień wzmianki — kontekst dla LLM.

    Dla długich dokumentów (transkrypty 50-100k znaków) obcięcie do text[:3000]
    gubiło kontekst wzmianek z dalszych części — LLM odpowiadał NONE dla osób
    i miejsc realnie omawianych (defekt znaleziony w E2E 2026-07-10, doc 9216).
    Dopasowanie po prefiksie bez wielkości liter, więc odmiana ("Macrona")
    znajduje się po formie bazowej ("Macron").
    """
    lowered = text.lower()
    needle = mention.lower()
    snippets = []
    start = 0
    while len(snippets) < max_snippets:
        idx = lowered.find(needle, start)
        if idx == -1:
            break
        snippets.append(text[max(0, idx - window):idx + len(needle) + window].strip())
        start = idx + len(needle)
    return "\n[...]\n".join(snippets)


def confirm_places_with_llm(text: str, title: str, candidate_names: list[str]) -> list[str]:
    """Z listy zweryfikowanych geokoderem miejsc wybierz te WYRAŹNIE omawiane w artykule.

    Ten sam wzorzec co extract_countries_hybrid: LLM dostaje zamkniętą listę
    kandydatów (nie może wymyślić miejsca spoza niej) i ocenia wyłącznie
    istotność w kontekście artykułu — fakt istnienia miejsca potwierdził już
    geokoder (library/place_verification.py). Zwraca podzbiór candidate_names.
    """
    from library.ai import ai_ask

    if not candidate_names:
        return []

    # Kontekst: fragmenty wokół wzmianek każdego kandydata zamiast początku
    # tekstu — dla długich transkryptów początek nie zawiera wzmianek
    snippet_parts = []
    for name in candidate_names:
        snippet = _mention_snippets(text, name, max_snippets=1)
        if snippet:
            snippet_parts.append(f"--- {name} ---\n{snippet}")
    context = "\n\n".join(snippet_parts) if snippet_parts else text[:3000]

    names = ", ".join(candidate_names)
    prompt = (
        f"Poniżej są fragmenty artykułu wokół wzmianek miejsc-kandydatów. Wybierz TYLKO te miejsca,\n"
        f"które są WYRAŹNIE omawiane (nie tylko przelotnie wspomniane).\n\n"
        f"Kandydaci: {names}\n\n"
        f"Zwróć TYLKO wybrane nazwy dokładnie tak, jak podano na liście kandydatów, oddzielone przecinkami.\n"
        f"Jeśli żaden z kandydatów nie jest wyraźnie omawiany, zwróć pustą odpowiedź.\n\n"
        f"TYTUŁ: {title}\n\nFRAGMENTY:\n{context[:6000]}"
    )
    try:
        response = ai_ask(prompt, model=_tagging_model(), temperature=0.0, max_token_count=150,
                          operation="place_relevance")
        raw = response.response_text.strip()
        if not raw:
            return []
        by_lower = {n.lower(): n for n in candidate_names}
        result = []
        for item in raw.split(","):
            name = by_lower.get(item.strip().lower())
            if name and name not in result:
                result.append(name)
        return result
    except Exception as e:
        print(f"  OSTRZEŻENIE: potwierdzenie miejsc nie powiodło się: {e}")
        return []


def confirm_person_with_llm(text: str, title: str, mention: str, candidates: list[dict]) -> str | None:
    """Wybierz, który kandydat z Wikidaty to osoba wspomniana w artykule.

    Kandydaci: [{"qid", "label", "description"}, ...] — opis (zawód/funkcja)
    jest kontekstem do disambiguacji (np. Donald Tusk polityk vs jego ojciec).
    LLM dostaje zamkniętą listę i może odpowiedzieć NONE — wtedy None (osoba
    z artykułu to ktoś inny niż wszyscy kandydaci). Zwraca QID lub None.
    """
    from library.ai import ai_ask

    if not candidates:
        return None

    # Kontekst wokół wzmianek tej osoby — początek długiego dokumentu często
    # w ogóle jej nie zawiera i LLM błędnie odpowiadał NONE
    context = _mention_snippets(text, mention) or text[:3000]
    listing = "\n".join(f"{c['qid']}: {c['label']} — {c['description'] or 'brak opisu'}" for c in candidates)
    prompt = (
        f'Poniżej są fragmenty artykułu wokół wzmianek osoby "{mention}".\n'
        f"Z listy kandydatów wybierz tego, o którym faktycznie mowa w artykule.\n\n"
        f"Kandydaci:\n{listing}\n\n"
        f"Zwróć TYLKO identyfikator wybranego kandydata (np. Q946), bez wyjaśnień.\n"
        f"Jeśli żaden kandydat nie pasuje do kontekstu artykułu, zwróć NONE.\n\n"
        f"TYTUŁ: {title}\n\nFRAGMENTY:\n{context[:3000]}"
    )
    try:
        response = ai_ask(prompt, model=_tagging_model(), temperature=0.0, max_token_count=20,
                          operation="place_candidate_selection")
        raw = response.response_text.strip().upper()
        valid = {c["qid"] for c in candidates}
        for token in re.findall(r"Q\d+", raw):
            if token in valid:
                return token
        return None
    except Exception as e:
        print(f"  OSTRZEŻENIE: disambiguacja osoby nie powiodła się: {e}")
        return None


def extract_countries_hybrid(text: str, title: str) -> list[str]:
    """Wykryj kraje: najpierw gazetteer (bez LLM), potem LLM potwierdza kandydatów.

    Tańsze i bardziej precyzyjne niż extract_countries_with_llm(): gazetteer
    (library.country_gazetteer) wyszukuje kraje po nazwie/przymiotniku bez
    wywołania LLM. Jeśli nic nie znajdzie, LLM w ogóle nie jest wywoływany.
    Jeśli znajdzie kandydatów, LLM dostaje zamkniętą listę do potwierdzenia,
    które z nich są WYRAŹNIE omawiane (a nie tylko przelotnie wspomniane) —
    zamiast open-ended ekstrakcji LLM nie może "wymyślić" kraju spoza listy.
    """
    from library.ai import ai_ask
    from library.country_gazetteer import detect_countries

    candidates = detect_countries(f"{title}\n{text}")
    if not candidates:
        return []

    candidate_names = ", ".join(c.name_pl for c in candidates)
    prompt = (
        f"Przeczytaj poniższy artykuł. Z listy krajów-kandydatów wybierz TYLKO te, które są w nim\n"
        f"WYRAŹNIE omawiane (nie tylko przelotnie wspomniane).\n\n"
        f"Kandydaci: {candidate_names}\n\n"
        f"Zwróć TYLKO wybrane nazwy dokładnie tak, jak podano na liście kandydatów, oddzielone przecinkami.\n"
        f"Jeśli żaden z kandydatów nie jest wyraźnie omawiany, zwróć pustą odpowiedź.\n\n"
        f"TYTUŁ: {title}\n\nTREŚĆ:\n{text[:3000]}"
    )
    try:
        response = ai_ask(prompt, model=_tagging_model(), temperature=0.0, max_token_count=150,
                          operation="infrastructure_relevance")
        raw = response.response_text.strip()
        if not raw:
            return []
        by_name = {c.name_pl.lower(): c.slug for c in candidates}
        result = []
        for item in raw.split(","):
            slug = by_name.get(item.strip().lower())
            if slug and f"kraj-{slug}" not in result:
                result.append(f"kraj-{slug}")
        return result
    except Exception as e:
        print(f"  OSTRZEŻENIE: potwierdzenie krajów nie powiodło się: {e}")
        return []
