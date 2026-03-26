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
import subprocess
import sys
import textwrap
from datetime import datetime
from typing import Optional

from library.config_loader import load_config
from library.db.engine import get_session
from library.db.models import WebDocument
from library.stalker_web_documents_db_postgresql import WebsitesDBPostgreSQL
from library.article_extractor import process_article_with_llm_fallback, _detect_portal
from library.lenie_markdown import (
    links_correct, md_square_brackets_in_one_line,
    md_get_images_as_links, get_images_with_links_md, process_markdown_and_extract_links,
)

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OBSIDIAN_VAULT = r"C:\Users\ziutus\Obsydian\personal"
OBSIDIAN_KNOWLEDGE_DIR = os.path.join(OBSIDIAN_VAULT, "02-wiedza")
NOTES_DIR = os.path.join(_BACKEND_DIR, "tmp", "article_notes")


def clean_article_text(text: str, url: str = "") -> str:
    """Wyczyść wyekstrahowany markdown: napraw rozłamane tagi, usuń obrazki, reklamy, sekcje premium."""
    import re
    from library.article_extractor import _detect_portal, _find_footer_line

    # 1. Napraw wieloliniowe linki i tagi markdown
    text = links_correct(text)
    text = md_square_brackets_in_one_line(text)

    # 2. Usuń linki-obrazki [![](img)](url) i same obrazki ![](url)
    text, _, _ = md_get_images_as_links(text)
    text, _ = get_images_with_links_md(text)

    # 3. Odetnij od footer markera portalu (linki, waluty, kalkulatory itp.)
    portal = _detect_portal(url)
    footer_line = _find_footer_line(text, portal)
    if footer_line is not None:
        lines_all = text.splitlines()
        text = "\n".join(lines_all[:footer_line])

    # 4. Usuń picture[N]:"..." i link[N]:... inline referencje
    text = re.sub(r'picture\[\d+\]:"[^"]*"', '', text)
    text = re.sub(r'link\[\d+\]:[^\n]*', '', text)

    # 5. Usuń NBSP, wielokrotne spacje
    text = text.replace('\xa0', ' ')
    text = re.sub(' +', ' ', text)

    # 5. Usuń szum linia po linii
    lines = text.splitlines()
    cleaned = []
    skip_section = False
    skip_markers = {
        "### Więcej pogłębionych treści", "### Więcej treści premium dla Ciebie",
        "## Top 5 treści Premium", "## Najlepsze w premium",
        "## Czeka nas skok cen",  # money.pl wstawki reklamowe
    }

    for line in lines:
        stripped = line.strip()

        if stripped in skip_markers:
            skip_section = True
            continue

        # Koniec sekcji: następne pytanie dziennikarza (**...**) lub długi akapit
        if skip_section and stripped and (stripped.startswith("**") or
                                          (len(stripped) > 50 and not stripped.startswith("[")
                                           and not stripped.startswith("picture[")
                                           and not stripped.startswith("!"))):
            skip_section = False

        if skip_section:
            continue

        # Pomiń picture[N]:"..." referencje (mogą być na początku lub same w linii)
        if re.match(r'^picture\[\d+\]:', stripped):
            continue
        # Pomiń linie które są TYLKO picture refs (np. w środku tekstu)
        stripped_no_pictures = re.sub(r'picture\[\d+\]:"[^"]*"', '', stripped).strip()
        if not stripped_no_pictures and 'picture[' in stripped:
            continue

        # Pomiń link[N]: referencje
        if re.match(r'^link\[\d+\]:', stripped):
            continue

        # Pomiń frazy portalowe
        if stripped in ("Dalszy ciąg materiału pod wideo", "Posłuchaj artykułu",
                        "Skróć artykuł", "REKLAMAKONIEC REKLAMY", "REKLAMA",
                        "Lubię to", "Obserwuj", "Udostępnij", "Skomentuj",
                        "- x1 +", "x1", "Notowania", "Źródło artykułu:",
                        "[ ]"):
            continue
        if stripped.startswith("Audio generowane") or stripped.startswith("Dźwięk został wygenerowany"):
            continue
        if stripped.startswith("Udostępnij na X"):
            continue

        # Pomiń linie z samą liczbą
        if stripped.isdigit():
            continue

        # Pomiń linie z samymi tagami portalu: [tag](/tag/...) [tag](/tag/...)
        if re.match(r'^(\[[\w\s]+\]\(/tag/[\w-]+/[^)]*\)\s*)+\+?\d*$', stripped):
            continue

        cleaned.append(line)

    text = "\n".join(cleaned)

    # 6. Zwiń wielokrotne puste linie
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


def get_article_text(doc, session) -> Optional[str]:
    """Pobierz wyekstrahowany tekst artykułu z cache lub przez LLM."""
    cfg = load_config()
    cache_dir_base = cfg.get("CACHE_DIR") or "tmp/markdown"
    cache_dir = os.path.join(cache_dir_base, str(doc.id))

    # Szukaj w cache (kolejność: step_2 > llm_extracted > step_1)
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
        markdown_text = prepare_markdown(doc.id, doc, cache_dir)
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


def action_save_note(doc, article_text: str) -> Optional[str]:
    """Zapisz notatkę użytkownika + treść artykułu do pliku.

    Returns: ścieżka do pliku lub None
    """
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

    note_text = "\n".join(note_lines)

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


def action_view(article_text: str):
    """Wyświetl pełną treść artykułu w terminalu."""
    print("\n" + "=" * 60)
    print(article_text)
    print("=" * 60)
    print(f"  [{len(article_text)} znaków]")


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
               start_id: Optional[int] = None, limit: int = 50):
    """Interaktywny przegląd artykułów."""
    filtered = _get_documents(session, limit=limit, since=since, portal=portal)

    if start_id:
        # Znajdź pozycję startową
        start_idx = next((i for i, d in enumerate(filtered) if d.id == start_id), 0)
        filtered = filtered[start_idx:]

    if not filtered:
        print("Brak artykułów do przeglądu.")
        return

    print(f"\n{len(filtered)} artykułów do przeglądu. Komendy:")
    print("  [n]ext / Enter  - następny artykuł")
    print("  [v]iew          - pokaż treść artykułu")
    print("  [s]ave          - zapisz notatkę (co mnie zainteresowało) + artykuł do pliku")
    print("  [o]bsidian      - stwórz/zaktualizuj notatkę Obsidian teraz (Claude Code)")
    print("  [c]ompare       - porównaj z istniejącymi notatkami (Claude Code)")
    print("  [q]uit          - zakończ")
    print()

    for idx, doc in enumerate(filtered, 1):
        date_str = doc.created_at.strftime("%Y-%m-%d %H:%M") if doc.created_at else "????"
        detected_portal = _detect_portal(doc.url) or "?"

        print(f"\n--- [{idx}/{len(filtered)}] ID: {doc.id} ---")
        print(f"  Tytuł:   {doc.title}")
        print(f"  Data:    {date_str}")
        print(f"  Portal:  {detected_portal}")
        print(f"  URL:     {doc.url}")
        print(f"  Stan:    {doc.document_state}")
        print()

        article_text = None  # lazy load

        while True:
            try:
                action = input(f"  [{idx}] [n/v/s/o/c/q]: ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                print("\nPrzegląd zakończony.")
                return

            if action in ("n", "next", ""):
                break

            elif action in ("v", "view"):
                if article_text is None:
                    article_text = get_article_text(doc, session)
                if article_text:
                    action_view(article_text)
                else:
                    print("  Nie udało się pobrać treści artykułu.")
                continue

            elif action in ("s", "save"):
                if article_text is None:
                    article_text = get_article_text(doc, session)
                if article_text:
                    action_save_note(doc, article_text)
                else:
                    print("  Nie udało się pobrać treści artykułu.")
                break

            elif action in ("o", "obsidian"):
                if article_text is None:
                    article_text = get_article_text(doc, session)
                if article_text:
                    action_obsidian(doc, article_text)
                else:
                    print("  Nie udało się pobrać treści artykułu.")
                break

            elif action in ("c", "compare"):
                if article_text is None:
                    article_text = get_article_text(doc, session)
                if article_text:
                    action_compare(doc, article_text)
                else:
                    print("  Nie udało się pobrać treści artykułu.")
                continue

            elif action in ("q", "quit"):
                print("Przegląd zakończony.")
                return

            else:
                print("  Nieznana komenda. Użyj: n, o, c, v, q")


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
                       start_id=args.id, limit=args.limit)
    finally:
        session.close()


if __name__ == "__main__":
    main()
