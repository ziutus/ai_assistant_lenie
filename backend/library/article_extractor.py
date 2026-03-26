"""
Moduł do ekstrakcji treści artykułu z markdown za pomocą LLM (Bielik)
oraz generowania plików .regex.draft na podstawie wyników.

Flow:
1. Przytnij markdown (usuń oczywistą nawigację z początku)
2. Wyślij do Bielika z promptem ekstrakcji markerów granic
3. Na podstawie markerów znajdź granice artykułu w oryginalnym markdown
4. Wygeneruj plik .regex.draft do ręcznej weryfikacji
"""

import json
import logging
import re
import os

logger = logging.getLogger(__name__)

EXTRACTION_SYSTEM_PROMPT = """Jesteś ekspertem od analizy polskich portali informacyjnych. Twoim zadaniem jest zidentyfikowanie DOKŁADNYCH granic artykułu prasowego w tekście markdown.

Odpowiadaj WYŁĄCZNIE poprawnym JSON, bez żadnego dodatkowego tekstu, komentarzy ani formatowania."""

EXTRACTION_USER_PROMPT_TEMPLATE = """Przeanalizuj poniższy tekst markdown ze strony internetowej polskiego portalu informacyjnego. Tekst zawiera artykuł prasowy otoczony elementami portalu (nawigacja, reklamy, linki do innych artykułów, komentarze, emotki, stopka).

Twoim zadaniem jest znalezienie DOKŁADNYCH granic artykułu. Zwróć JSON z polami:

- "title": tytuł artykułu (nagłówek H1)
- "author": autor artykułu (imię i nazwisko, jeśli dostępne, w przeciwnym razie null)
- "date": data publikacji (jeśli dostępna, w przeciwnym razie null)
- "article_first_sentence": DOKŁADNY CYTAT pierwszego zdania treści artykułu. To jest pierwsze zdanie tekstu właściwego — NIE tytuł, NIE imię autora, NIE data. Zazwyczaj zaczyna się od opisu tematu lub osoby.
- "article_last_sentence": DOKŁADNY CYTAT ostatniego zdania lub akapitu artykułu. Artykuły prasowe często kończą się: notką biograficzną o rozmówcy/autorze, ostatnią wypowiedzią w wywiadzie, lub podsumowaniem. Szukaj OSTATNIEGO zdania PRZED elementami portalu takimi jak: "Dziękujemy, że przeczytałaś/eś", emotki/reakcje, tagi, sekcja "Zobacz również", linki do innych artykułów. Jeśli artykuł kończy się notką biograficzną (np. "jest ekspertem...", "pełnił funkcję...") — to jest część artykułu, uwzględnij ją.
- "tags": lista tagów/słów kluczowych artykułu (jeśli widoczne na stronie, np. jako linki na dole)

ZASADY:
1. article_first_sentence i article_last_sentence muszą być DOKŁADNYMI cytatami z tekstu — skopiuj je znak po znaku
2. Cytaty muszą mieć minimum 40 znaków
3. Treść artykułu NIE obejmuje: nawigacji portalu, sekcji "Top 5 treści Premium", "Więcej pogłębionych treści", "Więcej treści premium dla Ciebie", "Zobacz także", reklam, komentarzy, emotek/reakcji, "Dalszy ciąg materiału pod wideo"
4. Treść artykułu OBEJMUJE: tekst właściwy, cytaty (blockquote >), pytania dziennikarza (pogrubione **), odpowiedzi rozmówcy, śródtytuły, notki biograficzne na końcu

Tekst markdown:
---
{markdown_text}
---

JSON:"""


def _trim_markdown_navigation(markdown_text: str) -> str:
    """Przytnij oczywistą nawigację z początku markdown.

    Szuka ostatniego nagłówka H1 (#) — portale często mają kilka H1,
    a właściwy artykuł jest pod ostatnim. Zwraca tekst od 3 linii przed nim.
    Jeśli nie znajdzie H1, zwraca ostatnie 60% tekstu.
    """
    lines = markdown_text.splitlines()

    # Znajdź OSTATNI H1 (właściwy artykuł jest zwykle pod ostatnim)
    last_h1 = None
    for i, line in enumerate(lines):
        if line.startswith("# ") and len(line) > 10:
            last_h1 = i

    if last_h1 is not None:
        start = max(0, last_h1 - 3)
        return "\n".join(lines[start:])

    # Fallback: weź ostatnie 60%
    start = len(lines) * 4 // 10
    return "\n".join(lines[start:])


def _detect_portal(url: str) -> str | None:
    """Rozpoznaj portal na podstawie URL."""
    if not url:
        return None
    url_lower = url.lower()
    if "onet.pl" in url_lower or "fakt.pl" in url_lower:
        return "onet"
    if "money.pl" in url_lower:
        return "money"
    if "wp.pl" in url_lower or "o2.pl" in url_lower:
        return "wp"
    if "interia.pl" in url_lower:
        return "interia"
    if "businessinsider.com.pl" in url_lower:
        return "businessinsider"
    return None


# Wzorce oznaczające KONIEC artykułu per portal.
# Tekst od pierwszego dopasowanego wzorca w dół jest odcinany.
PORTAL_FOOTER_MARKERS = {
    "onet": [
        "Dziękujemy, że przeczytałaś/eś",
        "*Dziękujemy, że przeczytałaś/eś",
        "*Masz ochotę na więcej?",
        "## Zobacz również",
        "## Zobacz także",
    ],
    "money": [
        "**Masz newsa, zdjęcie lub filmik?",
        "Oceń jakość naszego artykułu",
        "Wybrane dla Ciebie",
        "WALUTY",
        "KALKULATORY",
        "MONEY NA SKR",
    ],
    "wp": [
        "Wybrane dla Ciebie",
        "### Wybrane dla Ciebie",
        "**Masz newsa, zdjęcie lub filmik?",
        "**Czytaj także:**",
        "Oceń jakość naszego artykułu",
    ],
    "interia": [
        "Masz sugestie, uwagi albo widzisz na stronie błąd",
        "INTERIA.PL",
        "Polecjemy",
    ],
    "businessinsider": [
        "Dziękujemy, że przeczytałaś/eś",
        "## Autor",
    ],
}

# Wzorce wewnątrz artykułu do pominięcia per portal (sekcje reklamowe/premium)
PORTAL_SKIP_SECTIONS = {
    "onet": [
        "## Top 5 treści Premium",
        "### Więcej pogłębionych treści",
        "### Więcej treści premium dla Ciebie",
        "## Najlepsze w premium",
    ],
    "money": [],
    "wp": [],
    "interia": [],
    "businessinsider": [],
}

# Jednolinijkowe frazy do pominięcia per portal
PORTAL_SKIP_LINES = {
    "onet": [
        "Posłuchaj artykułu", "Skróć artykuł", "x1", "- x1 +",
        "Dalszy ciąg materiału pod wideo",
        "Więcej w Strefie Premium", "Obserwuj",
    ],
    "money": [
        "Dalszy ciąg materiału pod wideo",
    ],
    "wp": [
        "Dalszy ciąg materiału pod wideo",
        "ZAPISZUDOSTĘPNIJ",
    ],
    "interia": [
        "Dalszy ciąg materiału pod wideo",
        "Udostępnij",
    ],
    "businessinsider": [
        "Udostępnij artykuł",
        "Dalszy ciąg materiału pod wideo",
    ],
}


def _find_footer_line(text: str, portal: str | None) -> int | None:
    """Znajdź numer linii pierwszego markera stopki portalu w oryginalnym markdown."""
    universal_markers = [
        "## Zobacz również",
        "## Zobacz także",
        "Dziękujemy, że przeczytałaś/eś",
        "*Dziękujemy, że przeczytałaś/eś",
    ]

    markers = []
    if portal and portal in PORTAL_FOOTER_MARKERS:
        markers = PORTAL_FOOTER_MARKERS[portal][:]
    markers.extend(universal_markers)

    lines = text.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        for marker in markers:
            if stripped.startswith(marker):
                return i

    return None


def _cut_at_footer(text: str, portal: str | None) -> str:
    """Odetnij tekst od pierwszego markera stopki portalu."""
    # Markery uniwersalne (działają dla każdego portalu)
    universal_markers = [
        "## Zobacz również",
        "## Zobacz także",
    ]

    markers = universal_markers[:]
    if portal and portal in PORTAL_FOOTER_MARKERS:
        markers = PORTAL_FOOTER_MARKERS[portal] + markers

    lines = text.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        for marker in markers:
            if stripped.startswith(marker):
                logger.debug(f"Footer marker found at line {i}: {marker}")
                return "\n".join(lines[:i])

    return text


def _clean_markdown_for_llm(text: str, portal: str | None = None) -> str:
    """Usuń szum z markdown przed wysłaniem do LLM.

    Krok 1: Odetnij stopkę portalu (komentarze, "Zobacz również", tracking)
    Krok 2: Usuń sekcje reklamowe/premium wewnątrz artykułu
    Krok 3: Usuń obrazki, emotki, linie z samymi liczbami
    """
    # Krok 1: Odetnij od stopki
    text = _cut_at_footer(text, portal)

    skip_sections = PORTAL_SKIP_SECTIONS.get(portal, []) if portal else []
    skip_lines_set = set(PORTAL_SKIP_LINES.get(portal, [])) if portal else set()

    lines = text.splitlines()
    cleaned = []
    skip_section = False

    for line in lines:
        stripped = line.strip()

        # Krok 2: Pomiń sekcje portalowe (od nagłówka do następnej treści)
        if stripped in skip_sections:
            skip_section = True
            continue

        # Koniec sekcji portalowej: następne pytanie dziennikarza lub zwykły akapit
        if skip_section and stripped and (stripped.startswith("**") or
                                          (len(stripped) > 50 and not stripped.startswith("[") and
                                           not stripped.startswith("!") and not stripped.startswith("#"))):
            skip_section = False

        if skip_section:
            continue

        # Krok 3: Ogólne czyszczenie

        # Pomiń linie z samymi obrazkami markdown
        if stripped.startswith("![") and stripped.endswith(")"):
            continue

        # Pomiń linki-obrazki: [![](url)](url)
        if stripped.startswith("[![") and stripped.endswith(")"):
            continue

        # Pomiń linie z samą liczbą (np. "385" - liczba reakcji)
        if stripped.isdigit():
            continue

        # Pomiń frazy per portal
        if stripped in skip_lines_set:
            continue

        # Pomiń linie zaczynające się od "Audio generowane"
        if stripped.startswith("Audio generowane"):
            continue

        cleaned.append(line)

    return "\n".join(cleaned)


def _truncate_for_llm(text: str, max_chars: int = 15000) -> str:
    """Ogranicz tekst do max_chars znaków, przycinając od końca."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n[...tekst przycięty...]"


def extract_article_markers_with_llm(markdown_text: str, url: str = "",
                                     model: str = "speakleash/Bielik-11B-v3.0-Instruct") -> dict | None:
    """Wyślij markdown do LLM i pobierz markery granic artykułu.

    Returns:
        dict z polami: title, author, date, article_first_sentence, article_last_sentence, tags
        lub None w przypadku błędu
    """
    from library.api.arklabs.arklabs_completion import arklabs_get_completion

    portal = _detect_portal(url)
    logger.info(f"Detected portal: {portal or 'unknown'} (url: {url[:60]})")

    trimmed = _trim_markdown_navigation(markdown_text)
    cleaned = _clean_markdown_for_llm(trimmed, portal=portal)
    cleaned = _truncate_for_llm(cleaned)

    logger.info(f"LLM input: {len(markdown_text)} -> trimmed {len(trimmed)} -> cleaned {len(cleaned)} chars")

    prompt = EXTRACTION_USER_PROMPT_TEMPLATE.format(markdown_text=cleaned)

    try:
        response = arklabs_get_completion(
            prompt=prompt,
            model=model,
            max_tokens=800,
            temperature=0.1,
            system_prompt=EXTRACTION_SYSTEM_PROMPT,
            stateful=True,
        )

        logger.info(f"LLM extraction tokens: prompt={response.prompt_tokens}, "
                     f"completion={response.completion_tokens}, total={response.total_tokens}")

        response_text = response.response_text.strip()

        # Wyczyść odpowiedź - usuń ewentualne ```json``` wrappery
        if response_text.startswith("```"):
            response_text = re.sub(r'^```(?:json)?\s*', '', response_text)
            response_text = re.sub(r'\s*```$', '', response_text)

        markers = json.loads(response_text)

        # Walidacja: wymagane pola
        required_fields = ["article_first_sentence", "article_last_sentence"]
        missing = [f for f in required_fields if not markers.get(f)]
        if missing:
            logger.warning(f"LLM response missing fields: {missing}. Response: {response_text[:200]}")
            return None

        return markers

    except json.JSONDecodeError as e:
        logger.error(f"LLM response is not valid JSON: {e}\nResponse: {response.response_text}")
        return None
    except Exception as e:
        logger.error(f"LLM extraction failed: {e}")
        return None


def find_text_in_markdown(markdown_text: str, search_text: str) -> int | None:
    """Znajdź pozycję (numer linii) tekstu w markdown.

    Próbuje: exact match → match bez białych znaków → match po słowach.
    Returns: numer linii (0-based) lub None
    """
    if not search_text:
        return None

    lines = markdown_text.splitlines()

    # 1. Exact match
    for i, line in enumerate(lines):
        if search_text in line:
            return i

    # 2. Normalizacja białych znaków
    normalized_search = " ".join(search_text.split())
    for i, line in enumerate(lines):
        if normalized_search in " ".join(line.split()):
            return i

    # 3. Szukaj po pierwszych kilku słowach (min 5)
    words = normalized_search.split()
    if len(words) >= 5:
        partial = " ".join(words[:8])
        for i, line in enumerate(lines):
            if partial in " ".join(line.split()):
                return i

    return None


def extract_article_by_markers(markdown_text: str, markers: dict, url: str = "") -> str | None:
    """Wyodrębnij treść artykułu na podstawie markerów z LLM.

    Strategia hybrydowa:
    - Początek artykułu: z LLM (article_first_sentence)
    - Koniec artykułu: z LLM (article_last_sentence) LUB z footer markera portalu (co dalej)

    Returns: tekst artykułu lub None
    """
    first_sentence = markers.get("article_first_sentence", "")
    last_sentence = markers.get("article_last_sentence", "")

    start_line = find_text_in_markdown(markdown_text, first_sentence)
    end_line = find_text_in_markdown(markdown_text, last_sentence)

    if start_line is None:
        logger.warning(f"Cannot find article_first_sentence in markdown: {first_sentence[:80]}...")
        return None

    # Znajdź koniec na podstawie footer markera portalu
    portal = _detect_portal(url)
    footer_line = _find_footer_line(markdown_text, portal)

    if footer_line is not None:
        # Footer marker jest pewny (deterministyczny) — użyj go jako koniec
        # LLM marker traktuj jako fallback gdy brak footera
        end_line = footer_line - 1
        logger.info(f"Article end: footer line {footer_line}"
                     + (f", LLM line {find_text_in_markdown(markdown_text, last_sentence)}" if last_sentence else ""))
    elif end_line is not None:
        # Brak footera — użyj LLM markera
        logger.info(f"Article end: LLM line {end_line} (no footer marker found)")
    else:
        logger.warning(f"Cannot find article end: no footer marker, no LLM marker")
        return None

    # Cofnij się przez puste linie na końcu
    lines_list = markdown_text.splitlines()
    while end_line > start_line and not lines_list[end_line].strip():
        end_line -= 1

    if end_line <= start_line:
        logger.warning(f"article_last_sentence (line {end_line}) is before article_first_sentence (line {start_line})")
        return None

    lines = markdown_text.splitlines()
    # Dołącz linię z last_sentence
    article_lines = lines[start_line:end_line + 1]

    return "\n".join(article_lines)


def generate_regex_draft(markdown_text: str, markers: dict, output_path: str) -> bool:
    """Generuje plik .regex.draft na podstawie markerów granic artykułu.

    Analizuje kontekst przed article_first_sentence i po article_last_sentence,
    aby stworzyć wzorzec regex.

    Returns: True jeśli plik został zapisany
    """
    first_sentence = markers.get("article_first_sentence", "")
    last_sentence = markers.get("article_last_sentence", "")

    start_line = find_text_in_markdown(markdown_text, first_sentence)
    end_line = find_text_in_markdown(markdown_text, last_sentence)

    if start_line is None or end_line is None:
        logger.error("Cannot generate regex draft: markers not found in markdown")
        return False

    lines = markdown_text.splitlines()

    # Pobierz kontekst PRZED artykułem (5 linii) — to będzie "pre" pattern
    pre_start = max(0, start_line - 5)
    pre_lines = [l for l in lines[pre_start:start_line] if l.strip()]

    # Pobierz kontekst PO artykule (5 linii) — to będzie "post" pattern
    post_end = min(len(lines), end_line + 6)
    post_lines = [l for l in lines[end_line + 1:post_end] if l.strip()]

    # Buduj regex
    draft_lines = []
    draft_lines.append(f"# Auto-generated regex draft from LLM extraction")
    draft_lines.append(f"# Markers: title={markers.get('title', 'N/A')}")
    draft_lines.append(f"# Pre-article context (lines {pre_start+1}-{start_line}):")

    for line in pre_lines:
        escaped = _escape_for_regex(line)
        draft_lines.append(escaped)

    draft_lines.append("(?P<article_text>.*)")

    draft_lines.append(f"# Post-article context (lines {end_line+2}-{post_end}):")
    for line in post_lines:
        escaped = _escape_for_regex(line)
        draft_lines.append(escaped)

    # Zapisz wersję czytelną (draft)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(draft_lines))

    logger.info(f"Regex draft saved to {output_path}")

    # Zapisz też metadane z LLM obok
    meta_path = output_path.replace(".regex.draft", "_llm_markers.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({
            "markers": markers,
            "start_line": start_line,
            "end_line": end_line,
            "pre_context_lines": pre_lines,
            "post_context_lines": post_lines,
        }, f, ensure_ascii=False, indent=2)

    logger.info(f"LLM markers saved to {meta_path}")
    return True


def _escape_for_regex(line: str) -> str:
    """Zamień linię tekstu na wzorzec regex z escape specjalnych znaków.

    Zachowuje czytelność: zamiast pełnego re.escape, escapuje tylko znaki specjalne regex
    i zamienia zmienne elementy (np. daty, liczby) na wzorce.
    """
    # Escapuj znaki specjalne regex
    escaped = re.escape(line.strip())

    # Zamień escaped spacje na \s+
    escaped = escaped.replace(r"\ ", r"\s+")

    # Zamień daty typu "24 marca 2026, 12:15" na pattern
    escaped = re.sub(
        r"\d{1,2}\\s\+(?:stycznia|lutego|marca|kwietnia|maja|czerwca|lipca|sierpnia|"
        r"września|października|listopada|grudnia)\\s\+\d{4},\\s\+\d{2}:\d{2}",
        r"\\d{1,2}\\s+(?:stycznia|lutego|marca|kwietnia|maja|czerwca|lipca|sierpnia|"
        r"września|października|listopada|grudnia)\\s+\\d{4},\\s+\\d{2}:\\d{2}",
        escaped
    )

    # Zamień "X min czytania" na pattern
    escaped = re.sub(r"\d+\\s\+min\\s\+czytania", r"\\d+\\s+min\\s+czytania", escaped)

    # Zamień liczby (np. reakcje "385") na \d+
    escaped = re.sub(r'^\d+$', r'\\d+', escaped)

    return escaped


def process_article_with_llm_fallback(markdown_text: str, document_id: int,
                                       cache_dir: str, url: str,
                                       model: str = "speakleash/Bielik-11B-v3.0-Instruct") -> str | None:
    """Główna funkcja fallback: ekstrakcja artykułu przez LLM + generowanie regex draft.

    Returns: wyodrębniony tekst artykułu lub None
    """
    logger.info(f"document_id: {document_id} Starting LLM fallback extraction")

    # 1. Wyślij do LLM po markery (max 2 próby)
    markers = None
    for attempt in range(2):
        markers = extract_article_markers_with_llm(markdown_text, url=url, model=model)
        if markers is not None:
            break
        logger.warning(f"document_id: {document_id} LLM attempt {attempt + 1} failed, "
                       f"{'retrying' if attempt == 0 else 'giving up'}")

    if markers is None:
        logger.error(f"document_id: {document_id} LLM extraction returned no markers after 2 attempts")
        return None

    logger.info(f"document_id: {document_id} LLM markers: title={markers.get('title', 'N/A')}, "
                f"author={markers.get('author', 'N/A')}")

    # 2. Wyodrębnij artykuł na podstawie markerów
    article_text = extract_article_by_markers(markdown_text, markers, url=url)
    if article_text is None:
        logger.error(f"document_id: {document_id} Cannot extract article by LLM markers")
        return None

    # 3. Zapisz wyekstrahowany artykuł
    article_path = os.path.join(cache_dir, f"{document_id}_llm_extracted_article.md")
    with open(article_path, "w", encoding="utf-8") as f:
        f.write(article_text)
    logger.info(f"document_id: {document_id} LLM extracted article saved to {article_path}")

    # 4. Wygeneruj regex draft (w cache_dir, do ręcznej weryfikacji)
    from urllib.parse import urlparse
    domain = urlparse(url).netloc.replace(".", "_").replace("www_", "")
    draft_path = os.path.join(cache_dir, f"{domain}_{document_id}.regex.draft")
    generate_regex_draft(markdown_text, markers, draft_path)

    return article_text
