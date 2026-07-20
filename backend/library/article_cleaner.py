"""Czyszczenie wyekstrahowanego markdownu artykułu z artefaktów portali.

Główne wejście: clean_article_text(text, url) — zwraca dict {text, links, images}.
Obrazki i linki są zamieniane na markery [imgN] / [linkN], a ich metadane
trafiają do osobnych list. Reguły czyszczenia: generyczne (wspólne dla
wszystkich portali) + specyficzne per portal (onet, money, wp, gazeta, bankier).

Wydzielone z imports/article_browser.py, aby logika była testowalna
i reużywalna w skryptach batch.
"""

import re

from library.article_extractor import _detect_portal, _find_footer_line, _find_start_line
from library.article_quality import photo_caption_candidates
from library.lenie_markdown import links_correct, md_square_brackets_in_one_line

_IMG_MARKER_RE = re.compile(r'^\[img(\d+)(?::\s*[^\]]*)?\]\s*$')


def _detect_h2_ads(text: str) -> set:
    """Wykryj nagłówki H2 z obrazkiem/video/playerem zaraz po nich (wstawki).
    Musi być wywołane PRZED usuwaniem obrazków."""
    lines = text.splitlines()
    h2_ad_titles = set()
    video_player_markers = {"Przewiń wstecz", "Odtwórz/Pauza", "Przewiń naprzód", "Wycisz"}
    for i, line in enumerate(lines):
        stripped = line.strip().replace('\xa0', ' ')
        if stripped.startswith("## "):
            next_nonempty = [lines[j].strip() for j in range(i + 1, min(i + 10, len(lines)))
                             if lines[j].strip()]
            if not next_nonempty:
                continue
            # H2 + obrazek/video embed
            if (next_nonempty[0].startswith("![")
                    or next_nonempty[0].startswith("[![")
                    or "wpimg.pl" in next_nonempty[0]
                    or "v.wp.pl" in next_nonempty[0]
                    or next_nonempty[0].startswith("[](blob:")):
                h2_ad_titles.add(stripped)
            # H2 + kontrolki video playera w kolejnych liniach
            elif any(m in set(next_nonempty) for m in video_player_markers):
                h2_ad_titles.add(stripped)
    return h2_ad_titles


# Wzorce linków wewnętrznych portali (tagi, kategorie — nie artykuły)
_PORTAL_INTERNAL_LINK_PATTERNS = [
    r'/wiadomosci/[\w-]+\.html$',     # money.pl tagi
    r'/tag/',                          # wp.pl/o2.pl tagi
    r'0%2C128956\.html\?tag=',        # wyborcza.pl tagi
    r'wiadomosci\.onet\.pl/[\w-]+$',  # onet tagi
    r'onet\.pl/premium$',             # onet "Więcej w Strefie Premium"
    r'onet\.pl/autorzy/',             # onet autorzy
    r'/archiwum/autor/',              # money.pl autorzy
    r'/autor/',                        # wp.pl autorzy
    r'(%2C|,)temat(%2C|,)',             # wp.pl tagi: /iran,temat,598... lub %2Ctemat%2C
]


def _is_portal_internal_link(url: str) -> bool:
    """Czy link jest wewnętrznym linkiem portalu (tag, kategoria, autor)?"""
    return any(re.search(p, url) for p in _PORTAL_INTERNAL_LINK_PATTERNS)


def _is_adjacent_tag_links_line(line: str) -> bool:
    """Czy linia składa się wyłącznie z co najmniej dwóch linków tagowych portalu."""
    link_re = re.compile(r'\[[^\]\n]+\]\(([^)\n]+)\)')
    matches = link_re.findall(line)
    if len(matches) < 2 or link_re.sub('', line).strip():
        return False
    urls = [match.split('"')[0].strip() for match in matches]
    return all(_is_portal_internal_link(url) for url in urls)


def _clean_lines_generic(lines: list[str], h2_ad_titles: set) -> list[str]:
    """Generyczne czyszczenie linia po linii — wspólne dla wszystkich portali."""
    cleaned = []
    skip_section = False
    skip_section_markers = {
        "### Więcej pogłębionych treści", "### Więcej treści premium dla Ciebie",
        "## Top 5 treści Premium", "## Najlepsze w premium",
        "## Czytaj także w BUSINESS INSIDER",
    }

    for line in lines:
        stripped = line.strip()

        # Sekcje do pominięcia (premium, wstawki H2+img)
        # Po replace_link linia może mieć [linkN] na końcu — usuń przed porównaniem
        stripped_no_links = re.sub(r'\s*\[link\d+\]', '', stripped).strip()
        if stripped in skip_section_markers or stripped_no_links in skip_section_markers \
                or stripped in h2_ad_titles or stripped_no_links in h2_ad_titles:
            skip_section = True
            continue
        # H2 z [linkN] = "Zobacz też" link, nie treść artykułu
        if stripped.startswith("## ") and re.search(r'\[link\d+\]$', stripped):
            continue
        if skip_section:
            # "Więcej w Strefie Premium" — koniec sekcji, ale też pomiń tę linię
            if "Więcej w Strefie Premium" in stripped:
                skip_section = False
                continue
            # Koniec sekcji: pytanie dziennikarza (**Tekst**) lub długi akapit
            # Ale nie **1**, **2** itp. (numeracja w sekcji premium)
            if stripped and stripped.startswith("**") and not re.match(r'^\*\*\d+\*\*', stripped):
                skip_section = False
            elif stripped and len(stripped) > 80 and not stripped.startswith("[") and not stripped.startswith("!"):
                skip_section = False
            else:
                continue

        # picture[N]:, link[N]:
        if re.match(r'^(picture|link)\[\d+\]:', stripped):
            continue

        # Markdown horizontal rules (---, ***, ___) — artefakty z konwersji HTML
        if re.match(r'^[-*_]{3,}\s*$', stripped) or stripped == "|":
            continue

        # Puste nagłówki markdown (np. "####" po usunięciu obrazka z pustym URL)
        if re.match(r'^#{1,6}\s*$', stripped):
            continue

        # Puste linie z samą liczbą (reakcje)
        if stripped.isdigit():
            continue

        # Frazy portalowe wspólne
        if stripped in ("Dalszy ciąg materiału pod wideo", "REKLAMAKONIEC REKLAMY",
                        "REKLAMA", "KONIEC REKLAMY", "Lubię to", "[ ]", "Rozwiń", "Zwiń"):
            continue

        # Kontrolki video playera
        if stripped in ("Przewiń wstecz", "Odtwórz/Pauza", "Przewiń naprzód", "Wycisz",
                        "Ustawienia", "NA ŻYWO", "Oglądaj z dźwiękiem", "Zamknij",
                        "Włącz / wyłącz pełny ekran"):
            continue
        # Timestamp video: "00:09 / 00:16" lub samodzielne "Oglądaj" + czas
        if re.match(r'^\d{2}:\d{2}\s*/\s*\d{2}:\d{2}$', stripped):
            continue
        if re.match(r'^Ogl[aą]daj\s*$', stripped) or re.match(r'^\d{2}:\d{2}$', stripped):
            continue
        # Warianty "Dalsza część artykułu pod wideo" (z kursywą, dwukropkiem)
        if "dalsza część artykułu pod wideo" in stripped.lower() or \
           "dalszy ciąg materiału pod wideo" in stripped.lower() or \
           "dalszy ciąg artykułu pod materiałem wideo" in stripped.lower() or \
           "dalsza część artykulu pod video" in stripped.lower():
            continue
        # "Czytaj także:" + link na tej samej lub następnej linii
        if stripped.startswith("**Czytaj także:**") or stripped.startswith("**Czytaj również:**"):
            continue
        if stripped.startswith("**Zobacz także:**") or stripped.startswith("* **Czytaj więcej:**"):
            continue

        # "Zobacz też" z obrazkiem: [[imgN...] tytuł](url) lub [[imgN...] tytuł [linkN]
        if stripped.startswith("[[img"):
            continue

        cleaned.append(line)

    return cleaned


def _clean_lines_onet(lines: list[str]) -> list[str]:
    """Czyszczenie specyficzne dla onet.pl/fakt.pl."""
    skip = {
        "Posłuchaj artykułu", "Skróć artykuł", "- x1 +", "x1", "Obserwuj",
        "Więcej pogłębionych treści", "Więcej treści premium dla Ciebie",
        "Więcej takich artykułów znajdziesz na stronie głównej Onetu",
        "Top 5 treści Premium", "CZYTAJ TAKŻE", "ZOBACZ RÓWNIEŻ",
        "Dodaj w Google", "Wróć na", "Jesteś w strefie",
    }
    cleaned = []
    in_top_premium = False
    for line in lines:
        stripped = line.strip()

        # Sekcja "Top treści w Premium": nagłówek + ponumerowane linki (1 Tytuł [linkN])
        if stripped == "Top treści w Premium":
            in_top_premium = True
            continue
        if in_top_premium:
            if not stripped:
                continue
            if re.match(r'^\d+\s+\S', stripped) and re.search(r'\[link\d+\]\s*$', stripped):
                continue
            in_top_premium = False  # koniec sekcji — przetwórz tę linię normalnie

        # Porównuj treść linii bez prefiksów nagłówkowych (#### Posłuchaj artykułu → Posłuchaj artykułu)
        stripped_content = re.sub(r'^#{1,6}\s+', '', stripped)
        if stripped_content in skip:
            continue
        if stripped.startswith("Zapytaj o więcej Onet Czat z AI"):
            continue
        # Przyciski prędkości audio playera: x2, x1.75, x1.5, x1.25, x0.75
        if re.match(r'^x[\d.]+$', stripped):
            continue
        # Wstawki premium: "**1** ### Tytuł [linkN]**2** ### ..."
        if re.match(r'^\*\*\d+\*\*\s+###\s+', stripped):
            continue
        # "Więcej w Strefie Premium [linkN]"
        if "Więcej w Strefie Premium" in stripped:
            continue
        if stripped.startswith("Audio generowane"):
            continue
        # Data publikacji: "17 marca 2026, 12:31"
        if re.match(r'^\d{1,2}\s+\w+\s+\d{4},?\s+\d{1,2}:\d{2}$', stripped):
            continue
        # Czas czytania: "1 min czytania", "5 min czytania"
        if re.match(r'^\d+\s+min\s+czytania$', stripped):
            continue
        # Reakcje: "[img1][img2]1,6 tys." lub "[img0][img1]385"
        if re.match(r'^(\[img\d+\])+[\d,]+(\s*tys\.)?$', stripped):
            continue
        # "Powiązane tematy: Karol Nawrocki Wołodymyr Zełenski ..."
        if stripped.startswith("Powiązane tematy:"):
            continue
        # Byline redakcyjny: "Opracowanie: Mateusz Bałuka"
        if re.match(r'^Opracowanie:\s+\S', stripped):
            continue
        # CTA rekomendacji: "**PRZECZYTAJ CAŁY TEKST** [linkN]", "**PRZECZYTAJ CAŁY WYWIAD**"
        if re.match(r'^\*\*PRZECZYTAJ CAŁY [^*]+\*\*(?:\s+\[link\d+\])?$', stripped):
            continue
        cleaned.append(line)
    return cleaned


def _clean_lines_money(lines: list[str]) -> list[str]:
    """Czyszczenie specyficzne dla money.pl."""
    skip_exact = {"Skomentuj", "Notowania", "Udostępnij", "Słuchaj", "Kopiuj link"}
    skip_startswith = ("Udostępnij na ", "Źródło zdjęć:", "Źródło artykułu:",
                       "oprac.", "Dźwięk został wygenerowany")
    cleaned = []
    skip_source_logo = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("Źródło artykułu:"):
            skip_source_logo = True
            continue
        if skip_source_logo:
            if not stripped:
                continue
            skip_source_logo = False
            if re.match(r'^[A-Z]$', stripped):
                continue
        if stripped in skip_exact:
            continue
        if any(stripped.startswith(s) for s in skip_startswith):
            continue
        if re.match(r'^[\w.+-]+@grupawp\.pl\s*o autorze$', stripped, re.IGNORECASE):
            continue
        # Samodzielna data: "24 marca 2026, 12:26"
        if re.match(r'^\d{1,2}\s+\w+\s+\d{4},?\s+\d{1,2}:\d{2}$', stripped):
            continue
        if re.match(r'^\d+\s+komentarz', stripped):
            continue
        # Tagi: "gospodarka elektrownia atomowa rosja +1" lub z markerami [linkN]
        tag_line = re.sub(r'\[link\d+\]', '', stripped).strip()
        if re.match(r'^[\w\sąćęłńóśźżĄĆĘŁŃÓŚŹŻ]+\+\d+$', tag_line):
            continue
        # "Zobacz też" — linia z [imgN: tytuł] i link do innego artykułu money.pl
        if re.match(r'^\[?\[img\d+:.*\].*money\.pl/', stripped):
            continue
        cleaned.append(line)
    return cleaned


def _clean_lines_wp(lines: list[str]) -> list[str]:
    """Czyszczenie specyficzne dla wp.pl/o2.pl/tech.wp.pl."""
    skip_exact = {"Skomentuj", "Słuchaj", "Udostępnij", "Kopiuj link",
                  "Zaloguj", "Obserwuj nas na:", "Wyłączono komentarze"}
    skip_startswith = ("Udostępnij na ", "Dźwięk został wygenerowany",
                       "Źródło zdjęć:", "Źródło artykułu:", "oprac.",
                       "Jako redakcja Wirtualnej Polski", "Redakcja serwisu o2")

    # Tagi rozbite na osobne linie (o2.pl): "sztuczna inteligencja" / "polska" / "+3"
    # — usuń samodzielny licznik "+N" i bezpośrednio poprzedzające go linie tagów
    tag_counter_re = re.compile(r'^\+\d+$')
    tag_word_re = re.compile(r'^[a-ząćęłńóśźż][a-ząćęłńóśźż ]{0,40}$')
    drop: set[int] = set()
    for i, line in enumerate(lines):
        if tag_counter_re.match(line.strip()):
            drop.add(i)
            j = i - 1
            while j >= 0:
                s = lines[j].strip()
                if not s:
                    j -= 1
                    continue
                if tag_word_re.match(s):
                    drop.add(j)
                    j -= 1
                else:
                    break
    lines = [line for k, line in enumerate(lines) if k not in drop]

    cleaned = []
    in_newsletter = False
    for line in lines:
        stripped = line.strip()
        if stripped == "PREMIUM Zapisz się na newsletter!":
            in_newsletter = True
            continue
        if in_newsletter:
            if stripped in {
                "Newsy, wywiady, śledztwa i reportaże w Twojej skrzynce co tydzień - zawsze za darmo.",
                "Zapisz mnie",
            }:
                if stripped == "Zapisz mnie":
                    in_newsletter = False
                continue
            in_newsletter = False
        if stripped in skip_exact:
            continue
        if any(stripped.startswith(s) for s in skip_startswith):
            continue
        if re.match(r'^[\w.+-]+@grupawp\.pl\s*o autorze$', stripped, re.IGNORECASE):
            continue
        if re.match(r'^\d+\s+komentarz', stripped):
            continue
        # Samodzielna data: "23 marca 2026, 06:15"
        if re.match(r'^\d{1,2}\s+\w+\s+\d{4},?\s+\d{1,2}:\d{2}$', stripped):
            continue
        # Tagi: "iran rakiety balistyczne europa +3" lub z markerami "iran [link3] rakiety +3"
        tag_line = re.sub(r'\[link\d+\]', '', stripped).strip()
        if re.match(r'^[\w\sąćęłńóśźżĄĆĘŁŃÓŚŹŻ]+\+\d+$', tag_line):
            continue
        # Autor wp.pl: "Imię Nazwisko, dziennikarz/ka Wirtualnej Polski"
        if "dziennikarz" in stripped.lower() and "wirtualnej polski" in stripped.lower():
            continue
        # Banner "Misja AI" itp.
        if stripped.startswith("Misja AI"):
            continue
        # Reklamy z gigantycznym tracking URL (>300 znaków)
        if stripped.startswith("[") and stripped.endswith(")") and len(stripped) > 300:
            continue
        cleaned.append(line)
    return cleaned


def _clean_lines_ithardware(lines: list[str]) -> list[str]:
    """Usuń kontrolki osadzonego playera ITHardware bez globalnych reguł Play/ad."""
    return [line for line in lines if line.strip() not in {"Play", "ad"}]


def _clean_lines_bankier(lines: list[str]) -> list[str]:
    """Czyszczenie specyficzne dla bankier.pl.

    Breadcrumb i podmenu sekcji różnią się treścią per kategoria artykułu
    (Giełda/Gospodarka/Podatki/...), więc zamiast dopasowania po dokładnym
    tekście rozpoznajemy je po kształcie: krótki wiersz zaczynający się od
    "Bankier.pl" (breadcrumb sklejony bez spacji) albo wiersz zawierający
    kilka charakterystycznych nazw sekcji podmenu naraz.
    """
    subnav_keywords = ("Notowania", "Kalendarium", "Dywidendy", "Narzędzia", "Portfel", "Forum")
    cleaned = []
    skip_source_value = False
    in_tags = False
    for line in lines:
        stripped = line.strip()

        if stripped == "Źródło:":
            skip_source_value = True
            continue
        if skip_source_value:
            if not stripped:
                continue
            skip_source_value = False
            continue

        if stripped == "tematy":
            in_tags = True
            continue
        if in_tags:
            if not stripped:
                in_tags = False
                continue
            if len(stripped) < 60:
                continue
            in_tags = False

        if stripped in ("publikacja", "ad"):
            continue
        if stripped.startswith("Bankier.pl") and len(stripped) < 80:
            continue
        if sum(kw in stripped for kw in subnav_keywords) >= 3:
            continue
        # Samodzielna data publikacji: "2026-02-25 08:10"
        if re.match(r'^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}$', stripped):
            continue

        cleaned.append(line)
    return cleaned


def _clean_lines_gazeta(lines: list[str]) -> list[str]:
    """Usuń śródtekstowe karty rekomendacji Gazeta.pl, zachowując dalszy artykuł."""
    cleaned = []
    in_recommendation = False

    for line in lines:
        stripped = line.strip()
        stripped_no_links = re.sub(r'\s*\[link\d+\]', '', stripped).strip()

        if re.match(r'^Otwórz galerię \(\d+\)$', stripped, re.IGNORECASE):
            continue
        if re.match(r'^przejdź na(?: \[link\d+\])?$', stripped, re.IGNORECASE):
            continue

        if stripped_no_links in ("Czytaj także:", "Czytaj również:"):
            in_recommendation = True
            continue

        if in_recommendation:
            if not stripped or stripped in ("SUBSKRYPCJA", "REKLAMA"):
                continue
            # Po karcie rekomendacji właściwy artykuł wraca jako zwykły,
            # odpowiednio długi akapit. Przetwórz go już normalnie.
            if len(stripped_no_links) >= 100 and not stripped.startswith(("[", "!")):
                in_recommendation = False
            else:
                continue

        cleaned.append(line)

    return cleaned


# Kategorie photo_caption_candidates rozpoznane po jednoznacznym słowie-kluczu
# agencji/licencji (nie po samej pozycji względem markera) — bezpieczne do
# usunięcia z treści. "image_credit"/"image_description" to fallback samej
# pozycji (linia tuż po [imgN], krótka, bez nagłówka) i bywa fałszywie
# dopasowany do zwykłego akapitu (zob. test_standalone_image_line_preserved_
# for_quality_and_collected) — dlatego NIE są tu usuwane hurtowo.
_STRICT_CAPTION_CATEGORIES = {
    "public_domain", "creative_commons", "own_or_private_archive",
    "illustrative", "stock", "agency",
}

_IMG_MARKER_ALT_RE = re.compile(r'^\[img\d+(?::\s*([^\]]*))?\]\s*$')


def _strip_photo_caption_lines(text: str, url: str) -> str:
    """Usuń z treści linie-podpisy/credity zdjęć, których dane trafiły już
    strukturalnie do document_images (_attach_image_captions) — zostawienie
    ich w tekście artykułu jest tylko duplikacją. Marker [imgN] zostaje.

    Dwa niezależne, bezpieczne sygnały:
    1. Kategoria z jednoznacznym słowem-kluczem (_STRICT_CAPTION_CATEGORIES).
    2. Para [linia-credit, linia dokładnie powtarzająca alt obrazka] tuż po
       markerze — sama linia-credit rzadko ma rozpoznawalne słowo-klucz
       (np. "Panthalassa/x / Wodne Sprawy"), ale jednoznaczne potwierdzenie
       daje kolejna linia będąca dosłownym powtórzeniem alt-textu — realna
       treść artykułu praktycznie nigdy nie powtarza dosłownie alt obrazka.
    """
    lines = text.splitlines()
    remove_idx = {
        item["line_index"] for item in photo_caption_candidates(text, url)
        if item["category"] in _STRICT_CAPTION_CATEGORIES
    }

    pending_alt: str | None = None
    pending_credit_idx: int | None = None
    lines_left = 0
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        marker = _IMG_MARKER_ALT_RE.match(stripped)
        if marker:
            alt = (marker.group(1) or "").strip()
            pending_alt = alt or None
            pending_credit_idx = None
            lines_left = 2 if pending_alt else 0
            continue
        if lines_left <= 0:
            pending_alt = None
            continue
        lines_left -= 1
        normalized = re.sub(r'\s+', ' ', stripped).casefold()
        normalized_alt = re.sub(r'\s+', ' ', pending_alt or '').casefold()
        if normalized == normalized_alt:
            remove_idx.add(index)
            if pending_credit_idx is not None:
                remove_idx.add(pending_credit_idx)
            pending_alt = None
            lines_left = 0
        elif pending_credit_idx is None and len(stripped) <= 120 and not stripped.startswith('#'):
            pending_credit_idx = index
        else:
            pending_alt = None
            lines_left = 0

    if not remove_idx:
        return text
    return "\n".join(line for index, line in enumerate(lines) if index not in remove_idx)


def _attach_image_captions(text: str, extracted_images: list[dict], url: str) -> None:
    """Dopisz caption_text/caption_category do extracted_images na podstawie linii
    sąsiadujących z markerem [imgN] w tekście — MUSI być wywołane zaraz po
    podstawieniu markerów (krok 3), zanim dalsze czyszczenie (portal/generyczne)
    zdąży usunąć linię podpisu z tekstu. Reużywa article_quality.photo_caption_candidates
    (ta sama klasyfikacja, co przy liczeniu kary za pochodzenie zdjęcia)."""
    candidates = photo_caption_candidates(text, url)
    pending_idx: int | None = None
    for item in candidates:
        if item["category"] == "image_marker":
            marker = _IMG_MARKER_RE.match(item["text"])
            pending_idx = int(marker.group(1)) if marker else None
            continue
        if pending_idx is not None and pending_idx < len(extracted_images):
            extracted_images[pending_idx]["caption_text"] = item["text"]
            extracted_images[pending_idx]["caption_category"] = item["category"]
        pending_idx = None


_BULLET_LINE_RE = re.compile(r'^[*-]\s+\S')

# Box "Poniżej streszczenie artykułu: Skrót przygotowany przez Onet Czat z AI,
# może zawierać błędy." generuje zawsze dokładnie 5 punktów (zweryfikowane na
# żywo na kilku artykułach onet.pl). Ekstrakcja LLM czasem gubi sam nagłówek
# boxu, ale zostawia te 5 punktów jako pozorny początek artykułu — prawdziwy
# lead (inaczej sformułowany, czasem pogrubiony, czasem nie) idzie zaraz po
# nich. Liczba dokładnie 5 jest tu jedynym bezpiecznym sygnałem: prawdziwe
# artykuły otwierające się wypunktowaniem nie mają aż tak przewidywalnej
# długości, więc inne liczby zostają nietknięte.
_AI_SUMMARY_BULLET_COUNT = 5


def _strip_leading_onet_ai_summary(text: str) -> str:
    """Usuń z początku tekstu wyciek 5-punktowego streszczenia Onet Czat z AI
    (nagłówek boxu bywa już wycięty wcześniej w ekstrakcji, punkty zostają)."""
    lines = text.splitlines()
    idx = 0
    while idx < len(lines) and not lines[idx].strip():
        idx += 1

    bullet_count = 0
    j = idx
    while j < len(lines) and _BULLET_LINE_RE.match(lines[j].strip()):
        bullet_count += 1
        j += 1

    if bullet_count != _AI_SUMMARY_BULLET_COUNT:
        return text
    return "\n".join(lines[:idx] + lines[j:])


def clean_article_text(text: str, url: str = "") -> dict:
    """Wyczyść wyekstrahowany markdown. Zwraca dict: {text, links, images}."""
    extracted_links = []
    extracted_images = []
    portal = _detect_portal(url)

    if portal == "onet":
        text = _strip_leading_onet_ai_summary(text)

    # 1. Napraw wieloliniowe linki i tagi markdown
    text = links_correct(text)
    text = md_square_brackets_in_one_line(text)

    # Karty rekomendacji z linkowanym obrazkiem i nagłówkiem. Konwerter potrafi
    # zwrócić kilka kart bez separatora; md_square_brackets_in_one_line najpierw
    # odtwarza ich granice. Usuwamy teraz każdą kartę jako osobną linię, zanim
    # prosty parser obrazków natrafi na zagnieżdżone nawiasy, np. "[ANALIZA]".
    text = "\n".join(
        line for line in text.splitlines()
        if not (line.strip().startswith("[![") and "#### " in line)
    )

    # Konwertery HTML -> Markdown potrafią zwrócić blok tagów bez separatorów:
    # [tag 1](/tag/1)[tag 2](/tag/2). Usuń wyłącznie linie złożone w całości
    # z co najmniej dwóch linków rozpoznanych jako tagi/kategorie portalu.
    text = "\n".join(
        line for line in text.splitlines()
        if not _is_adjacent_tag_links_line(line.strip())
    )

    # 2. Wykryj H2+obrazek wstawki PRZED usuwaniem obrazków
    h2_ad_titles = _detect_h2_ads(text)

    # 3. Wyodrębnij obrazki → markery [imgN]
    # Pomijaj emotki, ikony, tracking pixele, duplikaty
    _skip_image_patterns = [
        "onetmobilemainpage/emotion/",
        "onetmobilemainpage/onet30/subServiceLogos/",
    ]
    _seen_image_urls = set()

    def replace_image(m):
        alt = m.group(1).strip()
        img_url = m.group(2).strip()
        # Artefakty z konwersji HTML: obrazki z pustym URL → usuń
        if not img_url:
            return ""
        # Pomijaj emotki, ikony portalu i bannery reklamowe
        if any(p in img_url for p in _skip_image_patterns):
            return ""
        if alt and alt.lower().startswith("misja ai"):
            return ""
        # Pomijaj duplikaty (ten sam URL)
        if img_url in _seen_image_urls:
            return ""
        _seen_image_urls.add(img_url)
        # Pomijaj obrazki bez alt i bez rozszerzenia (prawdopodobnie tracking pixel)
        if not alt and not any(img_url.lower().endswith(ext) for ext in ('.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp')):
            return ""
        idx = len(extracted_images)
        extracted_images.append({"alt": alt, "url": img_url})
        return f"[img{idx}: {alt}]" if alt else f"[img{idx}]"

    text = re.sub(r'!\[([^\]]*)\]\(([^)]*)\)', replace_image, text)
    # Linki owijające markery img: [[imgN]](url) → [imgN]
    text = re.sub(r'\[(\[img\d+[^\]]*\])\]\([^)]+\)', lambda m: m.group(1), text)

    # 3b. Skojarz podpisy/credity z markerami, zanim dalsze czyszczenie
    # zdąży usunąć linię podpisu z tekstu.
    _attach_image_captions(text, extracted_images, url)

    # 3c. Usuń z treści jednoznacznie rozpoznane linie-podpisy/credity zdjęć —
    # dane trafiły już do extracted_images (document_images), zostawienie ich
    # w tekście artykułu jest tylko duplikacją.
    text = _strip_photo_caption_lines(text, url)

    # 4. Odetnij od footer markera portalu
    footer_line = _find_footer_line(text, portal)
    if footer_line is not None:
        text = "\n".join(text.splitlines()[:footer_line])

    # 4b. Odetnij nawigację przed artykułem (marker końca nawigacji/początku treści).
    # Aktywne tylko gdy tekst pochodzi z surowego markdown (step_1_all.md) — LLM/regexp
    # same wycinają nawigację, tu potrzebne dla fallbacku na surowy plik.
    start_line = _find_start_line(text, portal)
    if start_line is not None:
        lines_tmp = text.splitlines()
        new_start = start_line + 1
        while new_start < len(lines_tmp) and not lines_tmp[new_start].strip():
            new_start += 1
        text = "\n".join(lines_tmp[new_start:])

    # 5. Wyodrębnij linki → markery [linkN] (portalowe → sam tekst)
    def replace_link(m):
        link_text = m.group(1).strip()
        link_url = m.group(2).strip().split('"')[0].strip()
        if not link_text:
            return ""
        if _is_portal_internal_link(link_url):
            return link_text
        # Onet premium numerowane linki: "**1** ### Tytuł", "Więcej w Strefie Premium"
        if re.match(r'^\*\*\d+\*\*\s+###', link_text):
            return link_text
        if "Więcej w Strefie Premium" in link_text:
            return link_text
        # "Zobacz też" z obrazkiem lub nagłówkiem H2/H3
        if re.match(r'^\[img\d+', link_text):
            return link_text
        if link_text.startswith("## ") or link_text.startswith("### "):
            return ""
        # Reklamy natywne z gigantycznym tracking URL (>200 znaków, encoded)
        if len(link_url) > 200:
            return ""
        idx = len(extracted_links)
        extracted_links.append({"text": link_text, "url": link_url})
        return f"{link_text} [link{idx}]"

    text = re.sub(r'\[([^\]]*)\]\(([^)]+)\)', replace_link, text)

    # 6. Usuń stare referencje z document_md_decode i osierocone markery
    text = re.sub(r'picture\[\d+\]:"[^"]*"', '', text)
    text = re.sub(r'link\[\d+\]:[^\n]*', '', text)
    # Osierocone [imgN] / [imgN: opis] — markery bez odpowiadającego obrazka
    # (np. z tekstu zapisanego do DB lub po odfiltrowaniu emotek)
    def _clean_orphan_img(m):
        try:
            idx = int(re.search(r'\d+', m.group(0)).group())
            if idx < len(extracted_images):
                return m.group(0)  # zachowaj — ma odpowiadający obrazek
        except (ValueError, AttributeError):
            pass
        return ""  # usuń osierocony
    text = re.sub(r'\[img\d+(?::[^\]]*)?\]', _clean_orphan_img, text)

    # 7. Normalizacja
    text = text.replace('\xa0', ' ')
    text = re.sub(' +', ' ', text)

    # 8. Czyszczenie linia po linii: generyczne + per-portal
    lines = text.splitlines()
    lines = _clean_lines_generic(lines, h2_ad_titles)

    if portal == "onet":
        lines = _clean_lines_onet(lines)
    elif portal == "money":
        lines = _clean_lines_money(lines)
    elif portal == "wp":
        lines = _clean_lines_wp(lines)
    elif portal == "gazeta":
        lines = _clean_lines_gazeta(lines)
    elif portal == "bankier":
        lines = _clean_lines_bankier(lines)
    elif "ithardware.pl" in url.lower():
        lines = _clean_lines_ithardware(lines)

    text = "\n".join(lines)
    text = re.sub(r'\n{3,}', '\n\n', text)

    return {
        "text": text.strip(),
        "links": extracted_links,
        "images": extracted_images,
        "portal": portal,
    }
