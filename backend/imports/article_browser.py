#!/usr/bin/env python3
"""Browse articles from Lenie DB and create/update Obsidian notes via Claude Code.

Usage:
    cd backend
    python imports/article_browser.py --list                              # List recent articles
    python imports/article_browser.py --list --state MD_SIMPLIFIED        # Filter by state
    python imports/article_browser.py --review --since 2026-03-20         # Interactive review
    python imports/article_browser.py --review --portal onet.pl           # Filter by portal
    python imports/article_browser.py --review --id 8786                  # Start from specific article
"""

import argparse
import os
import re
import subprocess
import sys
import textwrap
from datetime import datetime
from typing import Optional

from sqlalchemy import text as text_sql

from library.config_loader import load_config
from library.db.engine import get_session
from library.db.models import WebDocument
from library.stalker_web_documents_db_postgresql import WebsitesDBPostgreSQL
from library.article_extractor import process_article_with_llm_fallback, _detect_portal
from library.lenie_markdown import (
    links_correct, md_square_brackets_in_one_line, md_get_images_as_links,
)

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OBSIDIAN_VAULT = r"C:\Users\ziutus\Obsydian\personal"
OBSIDIAN_KNOWLEDGE_DIR = os.path.join(OBSIDIAN_VAULT, "02-wiedza")
NOTES_DIR = os.path.join(_BACKEND_DIR, "tmp", "article_notes")


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
    r',temat,',                        # wp.pl tagi: /iran,temat,598...
]


def _is_portal_internal_link(url: str) -> bool:
    """Czy link jest wewnętrznym linkiem portalu (tag, kategoria, autor)?"""
    return any(re.search(p, url) for p in _PORTAL_INTERNAL_LINK_PATTERNS)


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

        # Puste linie z samą liczbą (reakcje)
        if stripped.isdigit():
            continue

        # Frazy portalowe wspólne
        if stripped in ("Dalszy ciąg materiału pod wideo", "REKLAMAKONIEC REKLAMY",
                        "REKLAMA", "Lubię to", "[ ]"):
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
           "dalszy ciąg materiału pod wideo" in stripped.lower():
            continue
        # "Czytaj także:" + link na tej samej lub następnej linii
        if stripped.startswith("**Czytaj także:**") or stripped.startswith("**Czytaj również:**"):
            continue

        # Linia z samymi [imgN] markerami (osierocone po usunięciu kontekstu)
        if stripped.startswith("[img") and not any(c.isalpha() for c in re.sub(r'\[img\d+[^\]]*\]', '', stripped)):
            continue

        # "Zobacz też" z obrazkiem: [[imgN...] tytuł](url) lub [[imgN...] tytuł [linkN]
        if stripped.startswith("[[img"):
            continue

        cleaned.append(line)

    return cleaned


def _clean_lines_onet(lines: list[str]) -> list[str]:
    """Czyszczenie specyficzne dla onet.pl/fakt.pl."""
    skip = {"Posłuchaj artykułu", "Skróć artykuł", "- x1 +", "x1", "Obserwuj"}
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if stripped in skip:
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
        cleaned.append(line)
    return cleaned


def _clean_lines_money(lines: list[str]) -> list[str]:
    """Czyszczenie specyficzne dla money.pl."""
    skip_exact = {"Skomentuj", "Notowania", "Udostępnij"}
    skip_startswith = ("Udostępnij na X", "Źródło zdjęć:", "Źródło artykułu:",
                       "oprac.", "Dźwięk został wygenerowany")
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if stripped in skip_exact:
            continue
        if any(stripped.startswith(s) for s in skip_startswith):
            continue
        # Samodzielna data: "24 marca 2026, 12:26"
        if re.match(r'^\d{1,2}\s+\w+\s+\d{4},?\s+\d{1,2}:\d{2}$', stripped):
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
    skip_exact = {"Skomentuj", "Udostępnij"}
    skip_startswith = ("Udostępnij na X", "Dźwięk został wygenerowany",
                       "Źródło zdjęć:", "Źródło artykułu:", "oprac.")
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if stripped in skip_exact:
            continue
        if any(stripped.startswith(s) for s in skip_startswith):
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


def clean_article_text(text: str, url: str = "") -> dict:
    """Wyczyść wyekstrahowany markdown. Zwraca dict: {text, links, images}."""
    from library.article_extractor import _detect_portal, _find_footer_line

    extracted_links = []
    extracted_images = []
    portal = _detect_portal(url)

    # 1. Napraw wieloliniowe linki i tagi markdown
    text = links_correct(text)
    text = md_square_brackets_in_one_line(text)

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

    text = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', replace_image, text)
    # Linki owijające markery img: [[imgN]](url) → [imgN]
    text = re.sub(r'\[(\[img\d+[^\]]*\])\]\([^)]+\)', lambda m: m.group(1), text)

    # 4. Odetnij od footer markera portalu
    footer_line = _find_footer_line(text, portal)
    if footer_line is not None:
        text = "\n".join(text.splitlines()[:footer_line])

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
        # "Zobacz też" z obrazkiem: "[imgN...] ## Tytuł" lub "[imgN] Tytuł"
        if re.match(r'^\[img\d+', link_text):
            return link_text
        # Reklamy natywne z gigantycznym tracking URL (>200 znaków, encoded)
        if len(link_url) > 200:
            return ""
        idx = len(extracted_links)
        extracted_links.append({"text": link_text, "url": link_url})
        return f"{link_text} [link{idx}]"

    text = re.sub(r'\[([^\]]*)\]\(([^)]+)\)', replace_link, text)

    # 6. Usuń stare referencje z webdocument_md_decode i osierocone markery
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

    text = "\n".join(lines)
    text = re.sub(r'\n{3,}', '\n\n', text)

    return {
        "text": text.strip(),
        "links": extracted_links,
        "images": extracted_images,
    }


def get_article_text(doc, session) -> Optional[dict]:
    """Pobierz wyekstrahowany tekst artykułu z DB, cache lub przez LLM.
    Zwraca dict: {text, links, images} lub None."""

    # 1. Jeśli tekst jest w bazie (MD_SIMPLIFIED, EMBEDDING_EXIST) — użyj go
    if doc.text and len(doc.text) > 100 and doc.document_state in ("MD_SIMPLIFIED", "EMBEDDING_EXIST"):
        return clean_article_text(doc.text, doc.url)

    cfg = load_config()
    cache_dir_base = cfg.get("CACHE_DIR") or "tmp/markdown"
    cache_dir = os.path.join(cache_dir_base, str(doc.id))

    # 2. Szukaj w cache (kolejność: step_2 > llm_extracted > step_1)
    for suffix in ["_step_2_1_article.md", "_llm_extracted_article.md", "_step_1_all.md"]:
        cache_file = os.path.join(cache_dir, f"{doc.id}{suffix}")
        if os.path.isfile(cache_file):
            with open(cache_file, "r", encoding="utf-8") as f:
                text = f.read()
            if len(text) > 100:
                return clean_article_text(text, doc.url)

    # Szukaj markdown (step_1 lub .md)
    md_file = os.path.join(cache_dir, f"{doc.id}.md")
    step1_file = os.path.join(cache_dir, f"{doc.id}_step_1_all.md")
    markdown_text = None

    for path in [step1_file, md_file]:
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                markdown_text = f.read()
            break

    if not markdown_text:
        # Automatyczne pobranie z S3 i konwersja do markdown
        print(f"  Pobieram HTML z S3 i konwertuję do markdown...")
        from library.document_prepare import prepare_markdown, save_document_info
        os.makedirs(cache_dir, exist_ok=True)
        save_document_info(doc.id, doc, cache_dir)
        markdown_text = prepare_markdown(doc.id, doc, cache_dir, verbose=True)
        if not markdown_text:
            print(f"  Nie udało się pobrać artykułu z S3.")
            return None

    # Próba ekstrakcji przez LLM
    print(f"  Ekstrakcja artykułu przez LLM...")
    os.makedirs(cache_dir, exist_ok=True)
    result = process_article_with_llm_fallback(
        markdown_text=markdown_text,
        document_id=doc.id,
        cache_dir=cache_dir,
        url=doc.url,
    )
    if result:
        return clean_article_text(result, doc.url)
    return None


def call_claude(prompt: str):
    """Wywołaj Claude Code z promptem."""
    try:
        subprocess.run(["claude", "-p", prompt], check=False)
    except FileNotFoundError:
        print("  BŁĄD: komenda 'claude' nie znaleziona. Czy Claude Code jest zainstalowany?")


def _article_full_text(article: dict) -> str:
    """Złóż pełny tekst artykułu z linkami i obrazkami na dole (do zapisu/Claude)."""
    parts = [article["text"]]
    if article["links"]:
        parts.append("\n\n## Linki w artykule")
        for i, link in enumerate(article["links"]):
            parts.append(f"  [link{i}] {link['text']} — {link['url']}")
    if article["images"]:
        parts.append("\n\n## Obrazki w artykule")
        for i, img in enumerate(article["images"]):
            alt = img.get("alt", "")
            desc = f" — {alt}" if alt else ""
            parts.append(f"  [img{i}]{desc} — {img['url']}")
    return "\n".join(parts)


def _read_existing_note(doc_id: int) -> str | None:
    """Odczytaj istniejącą notatkę użytkownika (sekcja 'Moja notatka')."""
    note_file = os.path.join(NOTES_DIR, f"{doc_id}_note.md")
    if not os.path.isfile(note_file):
        return None
    with open(note_file, "r", encoding="utf-8") as f:
        content = f.read()
    if "## Moja notatka" in content:
        return content.split("## Moja notatka")[1].split("## Treść artykułu")[0].strip()
    return None


def action_save_note(doc, article_text: str) -> Optional[str]:
    """Zapisz/edytuj notatkę użytkownika + treść artykułu do pliku.

    Returns: ścieżka do pliku lub None
    """
    existing_note = _read_existing_note(doc.id)

    if existing_note:
        print(f"\n  Istniejąca notatka:")
        for line in existing_note.splitlines():
            print(f"     {line}")
        print()
        print("  [e]dytuj — napisz nową treść (zastąpi obecną)")
        print("  [d]opisz — dopisz nowy tekst pod istniejącym")
        print("  [Enter]  — anuluj")
        try:
            choice = input("  > ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print()
            return None

        if choice not in ("e", "edytuj", "d", "dopisz"):
            print("  Anulowano.")
            return None
        append_mode = choice in ("d", "dopisz")
    else:
        append_mode = False

    print("  Napisz co Cię zainteresowało (kilka linii, pusta linia kończy):")
    note_lines = []
    while True:
        try:
            line = input("  > ")
        except (KeyboardInterrupt, EOFError):
            print()
            return None
        if line.strip() == "":
            break
        note_lines.append(line)

    if not note_lines:
        print("  Pusta notatka — nie zapisano.")
        return None

    new_text = "\n".join(note_lines)
    # Napraw surrogaty z WSL/Windows terminal
    new_text = new_text.encode("utf-8", errors="surrogateescape").decode("utf-8", errors="replace")

    if append_mode and existing_note:
        note_text = existing_note + "\n\n" + new_text
    else:
        note_text = new_text

    os.makedirs(NOTES_DIR, exist_ok=True)
    note_file = os.path.join(NOTES_DIR, f"{doc.id}_note.md")

    with open(note_file, "w", encoding="utf-8") as f:
        f.write(f"# Notatka do artykułu: {doc.title}\n\n")
        f.write(f"- **Lenie ID**: {doc.id}\n")
        f.write(f"- **URL**: {doc.url}\n")
        f.write(f"- **Data**: {doc.created_at}\n")
        f.write(f"- **Obsidian vault**: {OBSIDIAN_KNOWLEDGE_DIR}\n\n")
        f.write(f"## Moja notatka\n\n")
        f.write(f"{note_text}\n\n")
        f.write(f"## Treść artykułu\n\n")
        f.write(f"{article_text}\n")

    print(f"  Zapisano: {note_file}")
    print(f"  Aby pracować nad notatką w Claude Code:")
    print(f"    claude \"przeczytaj @{note_file} i dodaj do mojego Obsidian vault\"")
    return note_file


def action_obsidian(doc, article_text: str):
    """Wywołaj Claude Code aby stworzył/zaktualizował notatkę Obsidian."""
    prompt = textwrap.dedent(f"""\
        Przeczytaj poniższy artykuł i wykonaj następujące kroki:

        1. Przeszukaj folder "{OBSIDIAN_KNOWLEDGE_DIR}" — szukaj istniejących notatek .md powiązanych tematycznie (użyj Grep/Glob po słowach kluczowych z artykułu)
        2. Jeśli znajdziesz powiązaną notatkę — zaproponuj dodanie nowych informacji z artykułu do odpowiedniej sekcji. Pokaż mi propozycję zmian i poczekaj na akceptację.
        3. Jeśli nie ma powiązanej notatki — zaproponuj stworzenie nowej w odpowiednim podfolderze z formatem:
           - Frontmatter z tagami (tags: wiedza/...)
           - Nagłówek H1
           - Treść ze strukturą (## sekcje, **pogrubienia** dla kluczowych myśli)
           - Na końcu: źródło z linkiem i ID z Lenie
        4. Zawsze dodaj na końcu sekcji/notatki linię źródła:
           Źródło: [{doc.title}]({doc.url}) (Lenie AI id={doc.id})

        Odpowiadaj po polsku.

        ---
        TYTUŁ: {doc.title}
        URL: {doc.url}
        DATA: {doc.created_at}
        LENIE ID: {doc.id}

        TREŚĆ ARTYKUŁU:
        {article_text}
    """)
    call_claude(prompt)


def action_compare(doc, article_text: str):
    """Wywołaj Claude Code aby porównał artykuł z istniejącymi notatkami."""
    prompt = textwrap.dedent(f"""\
        Przeczytaj poniższy artykuł, a następnie:

        1. Przeszukaj folder "{OBSIDIAN_KNOWLEDGE_DIR}" — znajdź notatki powiązane tematycznie (Grep/Glob)
        2. Porównaj informacje z artykułu z tym co jest w notatkach:
           - Co NOWEGO wnosi ten artykuł?
           - Czy coś jest SPRZECZNE z istniejącymi notatkami?
           - Czy artykuł POTWIERDZA wcześniejsze ustalenia?
        3. Podsumuj w 3-5 punktach po polsku

        NIE modyfikuj żadnych plików — tylko analiza.

        ---
        TYTUŁ: {doc.title}
        URL: {doc.url}
        LENIE ID: {doc.id}

        TREŚĆ ARTYKUŁU:
        {article_text}
    """)
    call_claude(prompt)


def _check_url_status(url: str) -> str:
    """Sprawdź HTTP status URL (HEAD request). Zwraca status string."""
    import requests
    try:
        r = requests.head(url, timeout=5, allow_redirects=True)
        if r.status_code == 200:
            return "OK"
        return f"{r.status_code}"
    except requests.RequestException:
        return "ERR"


def action_view(article: dict, check_urls: bool = False):
    """Wyświetl treść artykułu z listą linków i obrazków na dole."""
    text = article["text"]
    links = article["links"]
    images = article["images"]

    print("\n" + "=" * 60)
    print(text)
    print("=" * 60)

    if images:
        active_images = []
        dead_images = []
        for i, img in enumerate(images):
            if check_urls:
                status = _check_url_status(img["url"])
                img["_status"] = status
                if status == "OK":
                    active_images.append((i, img))
                else:
                    dead_images.append((i, img))
            else:
                active_images.append((i, img))

        if active_images:
            print(f"\n  Obrazki ({len(active_images)}):")
            for i, img in active_images:
                alt = img.get("alt", "")
                desc = f" — {alt}" if alt else ""
                print(f"    [img{i}]{desc}")
                print(f"           {img['url']}")
        if dead_images:
            print(f"\n  Obrazki niedostępne ({len(dead_images)}):")
            for i, img in dead_images:
                print(f"    [img{i}] {img['_status']} — {img['url']}")

    if links:
        if check_urls:
            active_links = []
            dead_links = []
            for i, link in enumerate(links):
                status = _check_url_status(link["url"])
                link["_status"] = status
                if status == "OK":
                    active_links.append((i, link))
                else:
                    dead_links.append((i, link))
        else:
            active_links = list(enumerate(links))
            dead_links = []

        if active_links:
            print(f"\n  Linki ({len(active_links)}):")
            for i, link in active_links:
                print(f"    [link{i}] {link['text']}")
                print(f"            {link['url']}")
        if dead_links:
            print(f"\n  Linki niedostępne ({len(dead_links)}):")
            for i, link in dead_links:
                print(f"    [link{i}] {link['_status']} — {link['text']} — {link['url']}")

    total_imgs = len(images)
    total_links = len(links)
    summary = f"  [{len(text)} znaków, {total_links} linków, {total_imgs} obrazków"
    if check_urls and images:
        dead_count = len([1 for img in images if img.get("_status", "OK") != "OK"])
        if dead_count:
            summary += f", {dead_count} niedostępnych"
    print(summary + "]")


def _refresh_db_connection(session):
    """Odśwież połączenie z bazą (mogło wygasnąć przy długim przeglądaniu)."""
    try:
        session.execute(text_sql("SELECT 1"))
        return True
    except Exception:
        session.rollback()
        try:
            session.execute(text_sql("SELECT 1"))
            return True
        except Exception as e:
            print(f"  BŁĄD: nie mogę połączyć się z bazą: {e}")
            return False


def action_save_to_db(doc, article: dict, session) -> bool:
    """Zapisz oczyszczony tekst do bazy, stwórz embedding, ustaw status."""
    from library.models.stalker_document_status import StalkerDocumentStatus
    from library.embedding import get_embedding
    from library.stalker_web_documents_db_postgresql import WebsitesDBPostgreSQL

    text_only = article["text"]
    cfg = load_config()
    embedding_model = cfg.get("EMBEDDING_MODEL") or "BAAI/bge-m3"

    print(f"  Zapisuję do bazy danych (ID: {doc.id})...")
    print(f"    Tekst: {len(text_only)} znaków")
    print(f"    Linki: {len(article['links'])}")
    print(f"    Obrazki: {len(article['images'])}")
    print(f"    Embedding model: {embedding_model}")
    print(f"    Status: {doc.document_state} → MD_SIMPLIFIED → EMBEDDING_EXIST")

    try:
        confirm = input("  Potwierdzasz? [y/N]: ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print()
        return False

    if confirm != "y":
        print("  Anulowano.")
        return False

    if not _refresh_db_connection(session):
        return False
    session.refresh(doc)

    # 1. Zapisz tekst
    if doc.text and not doc.text_raw:
        doc.text_raw = doc.text

    doc.text = text_only
    doc.document_state = StalkerDocumentStatus.MD_SIMPLIFIED.name

    # Zapisz autora z LLM markers jeśli dostępny
    cfg = load_config()
    cache_dir_base = cfg.get("CACHE_DIR") or "tmp/markdown"
    import glob as glob_mod
    markers_files = glob_mod.glob(os.path.join(cache_dir_base, str(doc.id), "*_llm_markers.json"))
    if markers_files and not doc.author:
        import json
        with open(markers_files[0], "r", encoding="utf-8") as f:
            markers_data = json.load(f)
        author = markers_data.get("markers", {}).get("author")
        if author:
            doc.author = author
            print(f"    Autor: {author}")

    try:
        session.commit()
        print(f"  Tekst zapisany. Status: MD_SIMPLIFIED")
    except Exception as e:
        session.rollback()
        print(f"  BŁĄD zapisu tekstu: {e}")
        return False

    # 2. Twórz embedding
    print(f"  Tworzę embedding...")
    try:
        wb_db = WebsitesDBPostgreSQL(session=session)
        # Usuń stare embeddingi dla tego dokumentu
        wb_db.embedding_delete(doc.id, embedding_model)
        session.commit()

        emb_result = get_embedding(embedding_model, text_only)

        if not doc.language:
            doc.language = 'pl'

        wb_db.embedding_add(
            website_id=doc.id,
            embedding=emb_result.embedding,
            language=doc.language,
            text=text_only,
            text_original=text_only,
            model=embedding_model,
        )

        doc.document_state = StalkerDocumentStatus.EMBEDDING_EXIST.name
        session.commit()
        print(f"  Embedding zapisany. Status: EMBEDDING_EXIST")
        return True

    except Exception as e:
        session.rollback()
        print(f"  BŁĄD embeddingu: {e}")
        print(f"  Tekst został zapisany (MD_SIMPLIFIED), ale embedding nie. Spróbuj ponownie.")
        return False


def _get_documents(session, limit: int = 50, since: Optional[str] = None,
                   portal: Optional[str] = None, state: Optional[str] = None) -> list:
    """Pobierz dokumenty z bazy z filtrami. Zwraca listę obiektów WebDocument."""
    wb_db = WebsitesDBPostgreSQL(session=session)
    doc_dicts = wb_db.get_list(document_type="webpage", limit=limit)

    results = []
    for d in doc_dicts:
        doc = WebDocument.get_by_id(session, d["id"])
        if doc is None:
            continue
        if portal and portal not in (doc.url or ""):
            continue
        if state and doc.document_state != state:
            continue
        if since:
            since_date = datetime.strptime(since, "%Y-%m-%d").date()
            if doc.created_at and doc.created_at.date() < since_date:
                continue
        results.append(doc)
    return results


def cmd_list(session, since: Optional[str] = None, portal: Optional[str] = None,
             state: Optional[str] = None, limit: int = 30):
    """Wyświetl listę artykułów z bazy."""
    documents = _get_documents(session, limit=limit, since=since, portal=portal, state=state)

    print(f"\nArtykuły w bazie ({len(documents)}):\n")

    for doc in documents:
        date_str = doc.created_at.strftime("%Y-%m-%d") if doc.created_at else "????"
        state_short = (doc.document_state or "?")[:15]
        title = (doc.title or "brak tytułu")[:80]
        print(f"  {doc.id:5d}  [{date_str}] [{state_short:15s}] {title}")


def cmd_review(session, since: Optional[str] = None, portal: Optional[str] = None,
               start_id: Optional[int] = None, limit: int = 50, auto_view: bool = False,
               check_urls: bool = False):
    """Interaktywny przegląd artykułów."""
    if start_id:
        # Gdy podano --id, zacznij od tego dokumentu (nawet jeśli nie jest na liście)
        doc = WebDocument.get_by_id(session, start_id)
        if doc is None:
            print(f"Dokument {start_id} nie znaleziony.")
            return
        filtered = [doc]
        # Dodaj kolejne dokumenty z listy (po start_id)
        all_docs = _get_documents(session, limit=limit, since=since, portal=portal)
        for d in all_docs:
            if d.id != start_id:
                filtered.append(d)
    else:
        filtered = _get_documents(session, limit=limit, since=since, portal=portal)

    if not filtered:
        print("Brak artykułów do przeglądu.")
        return

    print(f"{len(filtered)} artykułów do przeglądu.\n")

    idx = 0
    while 0 <= idx < len(filtered):
        doc = filtered[idx]
        date_str = doc.created_at.strftime("%Y-%m-%d %H:%M") if doc.created_at else "????"
        detected_portal = _detect_portal(doc.url) or "?"

        os.system("cls" if os.name == "nt" else "clear")
        print(f"--- [{idx + 1}/{len(filtered)}] ID: {doc.id} ---")
        print(f"  Tytuł:   {doc.title}")
        print(f"  Data:    {date_str}")
        print(f"  Portal:  {detected_portal}")
        print(f"  URL:     {doc.url}")
        print(f"  Stan:    {doc.document_state}")

        article = None  # lazy load (dict: text, links, images)

        if auto_view:
            article = get_article_text(doc, session)
            if article:
                action_view(article, check_urls=check_urls)
            else:
                print("  Nie udało się pobrać treści artykułu.")

        # Pokaż istniejącą notatkę jeśli jest
        note_file = os.path.join(NOTES_DIR, f"{doc.id}_note.md")
        if os.path.isfile(note_file):
            with open(note_file, "r", encoding="utf-8") as f:
                content = f.read()
            # Wyciągnij sekcję "Moja notatka"
            if "## Moja notatka" in content:
                note_part = content.split("## Moja notatka")[1].split("## Treść artykułu")[0].strip()
                print(f"\n  NOTATKA:")
                for line in note_part.splitlines():
                    print(f"     {line}")
            else:
                print(f"\n  NOTATKA: {note_file}")

        print()
        print("  [n]ext  [p]rev  [v]iew  [r]efresh  [d]b save  [s]ave note  [o]bsidian  [c]ompare  [q]uit")

        while True:
            try:
                action = input(f"  [{idx + 1}] > ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                print("\nPrzegląd zakończony.")
                return

            if action in ("n", "next", ""):
                idx += 1
                break

            elif action in ("p", "prev", "previous"):
                if idx > 0:
                    idx -= 1
                else:
                    print("  Jesteś na pierwszym artykule.")
                    continue
                break

            elif action in ("r", "refresh"):
                # Usuń cache LLM extracted i ponów analizę
                cache_dir_base_r = (load_config().get("CACHE_DIR") or "tmp/markdown")
                cache_dir_r = os.path.join(cache_dir_base_r, str(doc.id))
                import glob as glob_mod
                for f in glob_mod.glob(os.path.join(cache_dir_r, "*_llm_extracted_article.md")):
                    os.remove(f)
                    print(f"  Usunięto cache: {os.path.basename(f)}")
                article = None  # wymuś ponowną analizę
                print("  Cache wyczyszczony. Użyj [v] żeby zobaczyć ponownie wyekstrahowany tekst.")
                continue

            elif action in ("v", "view"):
                if article is None:
                    article = get_article_text(doc, session)
                if article:
                    action_view(article, check_urls=check_urls)
                else:
                    print("  Nie udało się pobrać treści artykułu.")
                continue

            elif action in ("d", "db"):
                if article is None:
                    article = get_article_text(doc, session)
                if article:
                    action_save_to_db(doc, article, session)
                else:
                    print("  Nie udało się pobrać treści artykułu.")
                continue

            elif action in ("s", "save"):
                if article is None:
                    article = get_article_text(doc, session)
                if article:
                    action_save_note(doc, _article_full_text(article))
                else:
                    print("  Nie udało się pobrać treści artykułu.")
                break

            elif action in ("o", "obsidian"):
                if article is None:
                    article = get_article_text(doc, session)
                if article:
                    action_obsidian(doc, _article_full_text(article))
                else:
                    print("  Nie udało się pobrać treści artykułu.")
                break

            elif action in ("c", "compare"):
                if article is None:
                    article = get_article_text(doc, session)
                if article:
                    action_compare(doc, _article_full_text(article))
                else:
                    print("  Nie udało się pobrać treści artykułu.")
                continue

            elif action in ("q", "quit"):
                print("Przegląd zakończony.")
                return

            else:
                print("  Nieznana komenda. Użyj: n, p, v, d, s, o, c, q")


def cmd_notes():
    """Wyświetl zapisane notatki do artykułów."""
    if not os.path.exists(NOTES_DIR):
        print("Brak zapisanych notatek.")
        return

    notes = sorted([f for f in os.listdir(NOTES_DIR) if f.endswith("_note.md")])
    if not notes:
        print("Brak zapisanych notatek.")
        return

    print(f"\nZapisane notatki ({len(notes)}):\n")
    for note_file in notes:
        path = os.path.join(NOTES_DIR, note_file)
        with open(path, "r", encoding="utf-8") as f:
            first_lines = [l.strip() for l in f.readlines()[:8] if l.strip()]

        title = first_lines[0].removeprefix("# Notatka do artykułu: ") if first_lines else "?"
        print(f"  {note_file}")
        print(f"    Tytuł: {title[:80]}")
        print(f"    Plik:  {path}")
        print(f"    Claude: claude \"przeczytaj @{path} i dodaj do mojego Obsidian vault\"")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Przeglądaj artykuły z Lenie DB i twórz notatki Obsidian")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="Lista artykułów")
    group.add_argument("--review", action="store_true", help="Interaktywny przegląd")
    group.add_argument("--notes", action="store_true", help="Pokaż zapisane notatki do przetworzenia")

    parser.add_argument("--since", default=None, help="Data od (YYYY-MM-DD)")
    parser.add_argument("--portal", default=None, help="Filtruj po portalu (np. onet.pl)")
    parser.add_argument("--state", default=None, help="Filtruj po stanie (np. MD_SIMPLIFIED)")
    parser.add_argument("--id", type=int, default=None, help="Zacznij od konkretnego ID")
    parser.add_argument("--view", action="store_true", help="Automatycznie pokaż treść przy --review")
    parser.add_argument("--check-urls", action="store_true", help="Sprawdź dostępność obrazków i linków")
    parser.add_argument("--limit", type=int, default=50, help="Maks. artykułów (domyślnie 50)")
    args = parser.parse_args()

    if args.notes:
        cmd_notes()
        return

    load_config()
    session = get_session()

    try:
        if args.list:
            cmd_list(session, since=args.since, portal=args.portal,
                     state=args.state, limit=args.limit)
        elif args.review:
            cmd_review(session, since=args.since, portal=args.portal,
                       start_id=args.id, limit=args.limit, auto_view=args.view,
                       check_urls=args.check_urls)
    finally:
        session.close()


if __name__ == "__main__":
    main()
