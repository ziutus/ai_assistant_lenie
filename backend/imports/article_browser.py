#!/usr/bin/env python3
"""Browse articles from Lenie DB and create/update Obsidian notes via Claude Code.

Usage:
    cd backend
    python imports/article_browser.py --list                              # List recent articles
    python imports/article_browser.py --list --state MD_SIMPLIFIED        # Filter by state
    python imports/article_browser.py --review --since 2026-03-20         # Interactive review
    python imports/article_browser.py --review --portal onet.pl           # Filter by portal
    python imports/article_browser.py --review --id 8786                  # Start from specific article
    python imports/article_browser.py --show --id 8799                    # Display article and exit (non-interactive)
    python imports/article_browser.py --show --id 8799 --check-urls       # Display with link validation
    python imports/article_browser.py --list --state NEED_MANUAL_REVIEW   # Articles needing manual review
    python imports/article_browser.py --list --state NEED_MANUAL_REVIEW --format ids    # Just IDs (for scripting)
    python imports/article_browser.py --list --state NEED_MANUAL_REVIEW --format short  # IDs + titles
    python imports/article_browser.py --review --not-cleaned                           # Fast flow: articles still cleanable by regexp+LLM (excludes NEED_MANUAL_REVIEW)
    python imports/article_browser.py --review --view --manual-review                 # Slow flow: dedicated pass over articles that need manual text cleanup (alias for --state NEED_MANUAL_REVIEW)
"""

import argparse
import os
import re
import subprocess
import sys
import textwrap
from datetime import datetime
from typing import Optional

from library.models.stalker_document_status import StalkerDocumentStatus

__version__ = "0.9.0"
# Changelog:
#   0.9.0 — usunięto akcje --review zdublowane z web UI (/webpage/:id, /chunks/:id):
#           [v]iew, [b]oundaries (tekst zawsze widoczny w formularzu / ArticleSourceComparison),
#           [e]ncje (EntitiesPanel — pełny odpowiednik, bogatszy o edycję/merge/wykluczenia),
#           [m]ark review (dropdown statusu + Zapisz), [s]ave note (pole documents.note),
#           [w]rite to db (stary pipeline: tagi+NER+1 embedding całości — zastąpiony
#           chunkowym pipeline'em document_analysis_service). Menu: n, p, r, d, o, c, k, q.
#   0.8.0 — usunięto --meta/--dump/--dump-md/--runs/--chunks/--chunk-text (JSON tryby dla
#           /obsidian-note) — oba skille (Claude Code i Codex) czytają teraz przez REST API
#           backendu zamiast ORM z Windowsa; --review/--list/--show/--notes bez zmian
#   0.7.0 — --runs/--chunks/--chunk-text: JSON zapytania o DocumentAnalysisRun/DocumentChunk/
#           DocumentTopicSection wprost z CLI (zamiast ad-hoc `python -c` heredoków wklejanych
#           w treść slash commandu /obsidian-note — łamały się pod PowerShell przy zagnieżdżonych
#           cudzysłowach)
#   0.6.0 — rozpoznawanie osób (etap 4): alias/Wikidata+LLM/fuzzy → document_persons
#           (library.person_registry; auto przy [w] i [e], confidence przy nazwiskach)
#   0.5.1 — weryfikacja miejsc (etap 3): geokoder LocationIQ + LLM → tagi miejsce-*
#           (library.place_verification; auto przy [w] i [e], ✓ przy zweryfikowanych)
#   0.5.0 — encje NER (osoby/miejsca): auto przy [w]rite to db, ręcznie [e]ncje w menu
#           (library.entity_service → tabela document_entities, docs/ner-integration-plan.md)
#   0.4.3 — ekstrakcja krajów: gazetteer (bez LLM) jako prescreen + LLM potwierdza kandydatów
#           (library.article_tagging.extract_countries_hybrid, zamiast open-ended extract_countries_with_llm)
#   0.4.2 — load_config() raz na poziomie modułu (cfg + CACHE_DIR_BASE zamiast 7 wywołań)
#   0.4.1 — refaktor: pipeline markdown+LLM → library/article_pipeline.py (wspólny z dynamodb_sync)
#   0.4.0 — refaktor: czyszczenie → library/article_cleaner.py, tagowanie LLM → library/article_tagging.py
#           (model z configa TAGGING_MODEL); _get_documents filtruje po stronie SQL (bez heurystyki limit*10)
#   0.3.6 — [v] wyświetla sam tekst bez granic HEAD/TAIL; [b] nadal pokazuje wycięty kontekst
#   0.3.5 — ekstrakcja krajów: auto przy tagach z COUNTRY_TAG_TRIGGERS, ręcznie [k]raje w menu
#   0.3.4 — get_article_text: early return dla youtube/movie (transkrypcja z DB, bez S3)
#   0.3.3 — dodano --meta: JSON z metadanymi bez pola text (oszczędność tokenów dla Claude Code)
#   0.3.2 — menu akcji drukowane przed każdym promptem (widoczne też po [v]/[b]/[r])
#   0.3.1 — [b] rozszerza kontekst HEAD/TAIL o +400 znaków (kolejne ~2 zdania) na każde naciśnięcie
#   0.3.0 — boundaries inline: HEAD przed tekstem, TAIL po tekście (wizualna ciągłość)
#   0.2.1 — boundaries auto-fetch step_1 z S3 gdy brak w cache; klawisz [b] bez Entera
#   0.2.0 — dodano --manual-review skrót, boundaries auto-view, zapis _step_1_all.md z S3
#   0.1.0 — wersja bazowa


from sqlalchemy import or_, select, text as text_sql
from sqlalchemy.exc import InternalError as SqlInternalError

from library.config_loader import load_config
from library.db.engine import get_session
from library.db.models import Document
from library.article_extractor import _detect_portal
from library.article_pipeline import ensure_raw_markdown, extract_article
from library.article_cleaner import clean_article_text
from library.article_tagging import extract_countries_hybrid

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OBSIDIAN_VAULT = r"C:\Users\ziutus\Obsydian\personal"
OBSIDIAN_KNOWLEDGE_DIR = os.path.join(OBSIDIAN_VAULT, "02-wiedza")
NOTES_DIR = os.path.join(_BACKEND_DIR, "tmp", "article_notes")

cfg = load_config()
CACHE_DIR_BASE = os.path.join(cfg.get("CACHE_DIR") or "tmp", "markdown")


def _getch_action(prompt: str) -> str:
    """Read a single keypress without Enter for known single-char actions.

    Falls back to input() if getch is not available or key is not a recognized action.
    """
    _SINGLE_KEYS = set("bnpvrwsdmockq")
    sys.stdout.write(prompt)
    sys.stdout.flush()
    try:
        if sys.platform == "win32":
            import msvcrt
            ch = msvcrt.getwch()
        else:
            import tty
            import termios
            fd = sys.stdin.fileno()
            old = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                ch = sys.stdin.read(1)
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)

        if ch in ("\r", "\n"):
            print()
            return ""
        if ch == "\x03":  # Ctrl+C
            raise KeyboardInterrupt
        if ch == "\x04":  # Ctrl+D
            raise EOFError

        if ch.lower() in _SINGLE_KEYS:
            print(ch)  # echo the character
            return ch.lower()

        # Not a single-key action — show what was typed and read the rest via input()
        return (ch + input()).strip().lower()
    except (ImportError, OSError):
        # Fallback: no terminal control available (e.g. piped input)
        return input().strip().lower()


def _get_cache_status(doc_id: int) -> str:
    """Zwraca jednoliniowy status plików cache dla artykułu: [md ✓/—] [llm ✓/—] [regexp ✓/—]"""
    cache_dir = os.path.join(CACHE_DIR_BASE, str(doc_id))
    checks = [
        ("md",     f"{doc_id}_step_1_all.md"),
        ("llm",    f"{doc_id}_llm_extracted_article.md"),
        ("regexp", f"{doc_id}_step_2_1_article.md"),
    ]
    parts = []
    for label, filename in checks:
        mark = "✓" if os.path.isfile(os.path.join(cache_dir, filename)) else "—"
        parts.append(f"[{label} {mark}]")
    return "  ".join(parts)


def get_article_text(doc, session) -> Optional[dict]:
    """Pobierz wyekstrahowany tekst artykułu z DB, cache lub przez LLM.
    Zwraca dict: {text, links, images} lub None."""

    # YouTube/movie: transkrypcja jest w doc.text — brak HTML w S3
    if doc.document_type in ("youtube", "movie"):
        if doc.text and len(doc.text) > 100:
            return {"text": doc.text.strip(), "links": [], "images": []}
        print("  Brak transkrypcji dla dokumentu YouTube.")
        return None

    # 1. Jeśli tekst jest w bazie (MD_SIMPLIFIED, EMBEDDING_EXIST) — użyj go
    if doc.text and len(doc.text) > 100 and doc.processing_status in ("MD_SIMPLIFIED", "EMBEDDING_EXIST"):
        return clean_article_text(doc.text, doc.url)

    cache_dir = os.path.join(CACHE_DIR_BASE, str(doc.id))

    # 2. Szukaj wyekstrahowanego artykułu w cache (regexp > LLM).
    # _step_1_all.md celowo pominięty — to surowy markdown całej strony, nie tekst artykułu.
    # Trafia do LLM jako wejście (niżej), nie jest zwracany bezpośrednio.
    for suffix in ["_step_2_1_article.md", "_llm_extracted_article.md"]:
        cache_file = os.path.join(cache_dir, f"{doc.id}{suffix}")
        if os.path.isfile(cache_file):
            with open(cache_file, "r", encoding="utf-8") as f:
                text = f.read()
            if len(text) > 100:
                return clean_article_text(text, doc.url)

    # 3. Surowy markdown (cache/S3 + zapis step_1) i ekstrakcja przez LLM
    print("  Ekstrakcja artykułu przez LLM...")
    markdown_text, result = extract_article(doc, cache_dir, verbose=True)
    if markdown_text is None:
        print("  Nie udało się pobrać artykułu z S3.")
        return None
    if result:
        return clean_article_text(result, doc.url)
    return None


def call_claude(prompt: str):
    """Wywołaj Claude Code z promptem."""
    try:
        subprocess.run(["claude", "-p", prompt], check=False)  # nosec B603 B607 — claude CLI, list args, no shell
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
        DATA: {doc.ingested_at}
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


def action_view(article: dict, check_urls: bool = False, cut_context: Optional[dict] = None):
    """Wyświetl treść artykułu z listą linków i obrazków na dole.

    Jeśli cut_context jest podany, HEAD jest drukowany przed tekstem (pokazując
    co wycięto PRZED artykułem), a TAIL po tekście (co wycięto PO).
    """
    text = article["text"]
    links = article["links"]
    images = article["images"]

    print("\n" + "=" * 60)
    _print_cut_head(cut_context)
    print(text)
    _print_cut_tail(cut_context)
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


def _trim_to_sentences(text: str, max_chars: int, from_end: bool) -> str:
    """Obetnij tekst do ~2 zdań, preferując granicę na kropce/znaku interpunkcyjnym."""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    if from_end:
        snippet = text[-max_chars:]
        # Spróbuj przyciąć do początku pierwszego pełnego zdania
        m = re.search(r"[.!?]\s+", snippet)
        if m:
            snippet = snippet[m.end():]
        return "…" + snippet
    else:
        snippet = text[:max_chars]
        m = None
        for match in re.finditer(r"[.!?](\s+|$)", snippet):
            m = match
        if m:
            snippet = snippet[:m.end()]
        return snippet + "…"


def compute_cut_context(doc, article: dict, context_chars: int = 400) -> Optional[dict]:
    """Policz HEAD/TAIL kontekst (tekst wycięty przed/po oczyszczonym artykule).

    Zwraca dict {head, head_len, tail, tail_len, error} lub None (twardy błąd).
    head/tail mogą być pustymi stringami — znaczy 'nic nie wycięto na tym końcu'.
    """
    cache_dir = os.path.join(CACHE_DIR_BASE, str(doc.id))

    # Czyta step_1 z cache; gdy brakuje — pobiera z S3, konwertuje i zapisuje
    try:
        raw = ensure_raw_markdown(doc, cache_dir, verbose=False)
    except Exception as e:
        return {"error": f"błąd pobierania: {e}"}
    if not raw:
        return {"error": "nie udało się pobrać surowego markdownu z S3"}

    clean = (article.get("text") or "").strip()
    if not clean:
        return {"error": "brak oczyszczonego tekstu"}

    def _anchor(s: str, n: int = 60) -> str:
        return re.sub(r"\s+", " ", s[:n]).strip()

    head_anchor = _anchor(clean, 60)
    tail_anchor = _anchor(clean[-60:], 60)
    raw_flat = re.sub(r"\s+", " ", raw)

    def _find_fuzzy(needle: str, haystack_flat: str, raw_text: str) -> Optional[tuple]:
        if not needle:
            return None
        pos_flat = haystack_flat.find(needle)
        if pos_flat < 0:
            short = needle[:30]
            pos_flat = haystack_flat.find(short)
            if pos_flat < 0:
                return None
            needle_len = len(short)
        else:
            needle_len = len(needle)
        first_word = needle.split(" ", 1)[0]
        start = raw_text.find(first_word, max(0, pos_flat - 20))
        if start < 0:
            start = raw_text.find(first_word)
        if start < 0:
            return None
        return (start, start + needle_len)

    head_pos = _find_fuzzy(head_anchor, raw_flat, raw)
    tail_pos = _find_fuzzy(tail_anchor, raw_flat, raw)

    result = {"error": None, "head": "", "head_len": 0, "tail": "", "tail_len": 0,
              "head_found": head_pos is not None, "tail_found": tail_pos is not None}

    if head_pos is not None:
        head_cut = raw[:head_pos[0]]
        result["head_len"] = len(head_cut)
        if head_cut.strip():
            result["head"] = _trim_to_sentences(head_cut, context_chars, from_end=True)

    if tail_pos is not None:
        tail_cut = raw[tail_pos[1]:]
        result["tail_len"] = len(tail_cut)
        if tail_cut.strip():
            result["tail"] = _trim_to_sentences(tail_cut, context_chars, from_end=False)

    return result


def _print_cut_head(ctx: Optional[dict]):
    """Wydrukuj blok HEAD — tekst wycięty przed właściwym artykułem."""
    if ctx is None:
        return
    if ctx.get("error"):
        print(f"\n  [boundaries niedostępne: {ctx['error']}]")
        return
    print()
    if not ctx["head_found"]:
        print("  ▲ [nie znaleziono początku oczyszczonego tekstu w raw]")
    elif ctx["head_len"] == 0:
        print("  ▲ [nic nie wycięto przed — artykuł zaczyna się od początku raw]")
    else:
        print(f"  ▲▲▲ WYCIĘTO PRZED ({ctx['head_len']} znaków) ▲▲▲")
        print(ctx["head"])
        print("  ▲▲▲ ─── koniec wyciętego — początek artykułu ─── ▲▲▲")


def _print_cut_tail(ctx: Optional[dict]):
    """Wydrukuj blok TAIL — tekst wycięty po właściwym artykule."""
    if ctx is None or ctx.get("error"):
        return
    if not ctx["tail_found"]:
        print("\n  ▼ [nie znaleziono końca oczyszczonego tekstu w raw]")
    elif ctx["tail_len"] == 0:
        print("\n  ▼ [nic nie wycięto po — artykuł kończy się na końcu raw]")
    else:
        print("  ▼▼▼ ─── koniec artykułu — początek wyciętego ─── ▼▼▼")
        print(ctx["tail"])
        print(f"  ▼▼▼ WYCIĘTO PO ({ctx['tail_len']} znaków) ▼▼▼")


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


def _get_documents(session, limit: int = 50, since: Optional[str] = None,
                   portal: Optional[str] = None, state: Optional[str] = None,
                   not_reviewed: bool = False, no_obsidian: bool = False,
                   not_cleaned: bool = False) -> list:
    """Pobierz dokumenty z bazy z filtrami (po stronie SQL). Zwraca listę obiektów Document.

    Najpierw jedno zapytanie o ID z pełnym filtrowaniem, potem ładowanie obiektów
    pojedynczo — dzięki temu dokument z uszkodzonym blokiem DB jest pomijany,
    a nie wywraca całego zapytania.
    """
    stmt = (
        select(Document.id)
        .where(Document.document_type == "webpage")
        .order_by(Document.ingested_at.desc())
        .limit(limit)
    )
    if portal:
        escaped = portal.replace("%", "\\%").replace("_", "\\_")
        stmt = stmt.where(Document.url.like(f"%{escaped}%", escape="\\"))
    if state:
        stmt = stmt.where(Document.processing_status == state)
    if since:
        since_date = datetime.strptime(since, "%Y-%m-%d")
        # Dokumenty bez ingested_at przechodzą filtr (jak w starym filtrowaniu w Pythonie)
        stmt = stmt.where(or_(Document.ingested_at.is_(None),
                              Document.ingested_at >= since_date))
    if not_reviewed:
        stmt = stmt.where(Document.reviewed_at.is_(None))
    if no_obsidian:
        stmt = stmt.where(or_(Document.obsidian_note_paths.is_(None),
                              Document.obsidian_note_paths == []))
    if not_cleaned:
        stmt = stmt.where(Document.processing_status.not_in([
            StalkerDocumentStatus.MD_SIMPLIFIED.name,
            StalkerDocumentStatus.READY_FOR_EMBEDDING.name,
            StalkerDocumentStatus.EMBEDDING_EXIST.name,
            # NEED_MANUAL_REVIEW is excluded from the fast flow — these articles need
            # dedicated manual text cleanup. Use `--state NEED_MANUAL_REVIEW` for that pass.
            StalkerDocumentStatus.NEED_MANUAL_REVIEW.name,
        ]))

    doc_ids = list(session.execute(stmt).scalars())

    results = []
    for doc_id in doc_ids:
        try:
            doc = Document.get_by_id(session, doc_id)
        except SqlInternalError as e:
            session.rollback()
            print(f"  OSTRZEŻENIE: pominięto dokument id={doc_id} — korupcja bloku DB: {e.orig}")
            continue
        if doc is not None:
            results.append(doc)
    return results


def cmd_list(session, since: Optional[str] = None, portal: Optional[str] = None,
             state: Optional[str] = None, limit: int = 30, fmt: str = "table",
             not_reviewed: bool = False, no_obsidian: bool = False,
             not_cleaned: bool = False):
    """Wyświetl listę artykułów z bazy."""
    documents = _get_documents(session, limit=limit, since=since, portal=portal, state=state,
                               not_reviewed=not_reviewed, no_obsidian=no_obsidian,
                               not_cleaned=not_cleaned)

    if fmt == "ids":
        # Compact format: one ID per line — useful as input for scripts/Claude Code
        for doc in documents:
            print(doc.id)
        return

    if fmt == "short":
        # ID + title — useful as input for Claude Code
        for doc in documents:
            title = (doc.title or "brak tytułu")[:100]
            print(f"{doc.id}\t{title}")
        return

    print(f"\nArtykuły w bazie ({len(documents)}):\n")

    for doc in documents:
        date_str = doc.ingested_at.strftime("%Y-%m-%d") if doc.ingested_at else "????"
        state_short = (doc.processing_status or "?")[:15]
        title = (doc.title or "brak tytułu")[:70]
        reviewed = doc.reviewed_at.strftime("%Y-%m-%d") if doc.reviewed_at else "-"
        obsidian_count = len(doc.obsidian_note_paths or [])
        print(f"  {doc.id:5d}  [{date_str}] [{state_short:15s}] R:{reviewed:10s} O:{obsidian_count} {title}")


def action_mark_reviewed(doc, session):
    """Oznacz artykuł jako przejrzany (reviewed_at = NOW())."""
    try:
        doc.reviewed_at = datetime.now()
        session.commit()
        print(f"  Oznaczono jako przejrzany: {doc.reviewed_at.strftime('%Y-%m-%d %H:%M')}")
    except Exception as e:
        session.rollback()
        print(f"  BŁĄD oznaczania: {e}")


def action_track_obsidian_path(doc, session):
    """Zapytaj użytkownika o ścieżkę notatki Obsidian i zapisz w DB."""
    try:
        note_path = input("  Ścieżka notatki Obsidian (pusta = pomiń): ").strip()
    except (KeyboardInterrupt, EOFError):
        return

    if not note_path:
        return

    if os.path.isabs(note_path):
        print("  UWAGA: ścieżka powinna być względna do vault Obsidian, nie absolutna.")
        return
    if not note_path.endswith(".md"):
        print("  UWAGA: ścieżka notatki Obsidian powinna kończyć się na .md")
        return

    try:
        paths = list(doc.obsidian_note_paths or [])
        paths.append(note_path)
        doc.obsidian_note_paths = paths
        if not doc.reviewed_at:
            doc.reviewed_at = datetime.now()
        session.commit()
        print(f"  Zapisano ścieżkę Obsidian ({len(paths)} notatek). Reviewed: {doc.reviewed_at.strftime('%Y-%m-%d %H:%M')}")
    except Exception as e:
        session.rollback()
        print(f"  BŁĄD zapisu ścieżki: {e}")


def cmd_show(session, article_id: Optional[int] = None, check_urls: bool = False):
    """Wyświetl artykuł (metadane + treść) i zakończ — tryb nieinteraktywny."""
    if article_id is None:
        print("ERROR: --show wymaga --id <ARTICLE_ID>")
        sys.exit(1)

    doc = Document.get_by_id(session, article_id)
    if doc is None:
        print(f"Dokument {article_id} nie znaleziony.")
        sys.exit(1)

    date_str = doc.ingested_at.strftime("%Y-%m-%d %H:%M") if doc.ingested_at else "????"
    detected_portal = _detect_portal(doc.url) or "?"

    print(f"--- ID: {doc.id} ---")
    print(f"  Tytuł:   {doc.title}")
    print(f"  Data:    {date_str}")
    print(f"  Portal:  {detected_portal}")
    print(f"  URL:     {doc.url}")
    print(f"  Stan:    {doc.processing_status}")
    print(f"  Cache:   {_get_cache_status(doc.id)}")
    print(f"  Typ:     {doc.document_type}")
    print(f"  Język:   {doc.language}")
    print(f"  Źródło:  {doc.discovery_source_name}")
    obsidian_paths = doc.obsidian_note_paths or []
    if obsidian_paths:
        print(f"  Obsidian: {len(obsidian_paths)} notatek")
        for op in obsidian_paths:
            print(f"    - {op}")
    if doc.tags:
        print(f"  Tagi:    {doc.tags}")
    reviewed_str = doc.reviewed_at.strftime("%Y-%m-%d %H:%M") if doc.reviewed_at else "nie"
    print(f"  Reviewed: {reviewed_str}")

    article = get_article_text(doc, session)
    if article:
        action_view(article, check_urls=check_urls)
    else:
        print("\n  Nie udało się pobrać treści artykułu.")


def cmd_review(session, since: Optional[str] = None, portal: Optional[str] = None,
               start_id: Optional[int] = None, limit: int = 50, auto_view: bool = False,
               check_urls: bool = False, not_reviewed: bool = False, no_obsidian: bool = False,
               not_cleaned: bool = False):
    """Interaktywny przegląd artykułów."""
    if start_id:
        # Gdy podano --id, zacznij od tego dokumentu (nawet jeśli nie jest na liście)
        doc = Document.get_by_id(session, start_id)
        if doc is None:
            print(f"Dokument {start_id} nie znaleziony.")
            return
        filtered = [doc]
        # Dodaj kolejne dokumenty z listy (po start_id)
        all_docs = _get_documents(session, limit=limit, since=since, portal=portal,
                                  not_reviewed=not_reviewed, no_obsidian=no_obsidian,
                                  not_cleaned=not_cleaned)
        for d in all_docs:
            if d.id != start_id:
                filtered.append(d)
    else:
        filtered = _get_documents(session, limit=limit, since=since, portal=portal,
                                  not_reviewed=not_reviewed, no_obsidian=no_obsidian,
                                  not_cleaned=not_cleaned)

    if not filtered:
        print("Brak artykułów do przeglądu.")
        return

    print(f"{len(filtered)} artykułów do przeglądu.\n")

    idx = 0
    while 0 <= idx < len(filtered):
        doc = filtered[idx]
        # Odśwież połączenie i przeładuj obiekt (mogło wygasnąć po długiej operacji
        # jak zapis embeddingu; session.commit() wygasza obiekty → lazy-load → błąd)
        if not _refresh_db_connection(session):
            print("  BŁĄD: utracono połączenie z bazą. Przerwano przeglądanie.")
            break
        try:
            session.refresh(doc)
        except Exception as e:
            print(f"  OSTRZEŻENIE: nie udało się odświeżyć dokumentu {doc.id}: {e}")
        date_str = doc.ingested_at.strftime("%Y-%m-%d %H:%M") if doc.ingested_at else "????"
        detected_portal = _detect_portal(doc.url) or "?"

        os.system("cls" if os.name == "nt" else "clear")  # nosec B605 — constant command, no user input
        print(f"--- [{idx + 1}/{len(filtered)}] ID: {doc.id} ---")
        print(f"  Tytuł:   {doc.title}")
        print(f"  Data:    {date_str}")
        print(f"  Portal:  {detected_portal}")
        print(f"  URL:     {doc.url}")
        print(f"  Stan:    {doc.processing_status}")
        print(f"  Cache:   {_get_cache_status(doc.id)}")
        obsidian_paths = doc.obsidian_note_paths or []
        if obsidian_paths:
            print(f"  Obsidian: {len(obsidian_paths)} notatek")
            for op in obsidian_paths:
                print(f"    - {op}")
        if doc.tags:
            print(f"  Tagi:    {doc.tags}")
        reviewed_str = doc.reviewed_at.strftime("%Y-%m-%d %H:%M") if doc.reviewed_at else "nie"
        print(f"  Reviewed: {reviewed_str}")

        article = None  # lazy load (dict: text, links, images)

        if auto_view:
            article = get_article_text(doc, session)
            if article:
                action_view(article, check_urls=check_urls, cut_context=None)
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
                print("\n  NOTATKA:")
                for line in note_part.splitlines():
                    print(f"     {line}")
            else:
                print(f"\n  NOTATKA: {note_file}")

        print()

        while True:
            print(f"  ID: {doc.id}  Status: {doc.processing_status}   (article_browser v{__version__})")
            print("  [n]ext  [p]rev  [r]efresh  [d]one/reviewed  [o]bsidian  [c]ompare  [k]raje  [q]uit")
            try:
                action = _getch_action(f"  [{idx + 1}] > ")
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
                # Usuń cache LLM extracted i ponów ekstrakcję
                cache_dir_r = os.path.join(CACHE_DIR_BASE, str(doc.id))
                import glob as glob_mod
                for f in glob_mod.glob(os.path.join(cache_dir_r, "*_llm_extracted_article.md")):
                    os.remove(f)
                    print(f"  Usunięto cache: {os.path.basename(f)}")
                article = None
                print("  Cache wyczyszczony. Pobieram tekst ponownie...")
                article = get_article_text(doc, session)
                if article:
                    ctx = compute_cut_context(doc, article)
                    action_view(article, check_urls=check_urls, cut_context=ctx)
                else:
                    print("  Nie udało się pobrać treści artykułu. Spróbuj [r]efresh ponownie za chwilę (problem z API).")
                continue

            elif action in ("d", "done"):
                action_mark_reviewed(doc, session)
                continue

            elif action in ("o", "obsidian"):
                if article is None:
                    article = get_article_text(doc, session)
                if article:
                    action_obsidian(doc, _article_full_text(article))
                    action_track_obsidian_path(doc, session)
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

            elif action in ("k", "kraje"):
                if article is None:
                    article = get_article_text(doc, session)
                if article:
                    text_only = _article_full_text(article)
                    print("  Wyciągam nazwy krajów z artykułu...")
                    country_tags = extract_countries_hybrid(text_only, doc.title or "")
                    if country_tags:
                        existing = [t for t in (doc.tags or "").split(",") if t.strip()]
                        existing_countries = {t for t in existing if t.startswith("kraj-")}
                        new_countries = [t for t in country_tags if t not in existing_countries]
                        all_tags = existing + new_countries
                        doc.tags = ",".join(all_tags)
                        try:
                            session.commit()
                            print(f"  Kraje dodane: {', '.join(new_countries)}")
                            print(f"  Tagi: {doc.tags}")
                        except Exception as e:
                            session.rollback()
                            print(f"  OSTRZEŻENIE: nie udało się zapisać tagów: {e}")
                    else:
                        print("  Nie wykryto nazw krajów.")
                else:
                    print("  Nie udało się pobrać treści artykułu.")
                continue

            elif action in ("q", "quit"):
                print("Przegląd zakończony.")
                return

            else:
                print("  Nieznana komenda. Użyj: n, p, r, d, o, c, k, q")


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
            first_lines = [line.strip() for line in f.readlines()[:8] if line.strip()]

        title = first_lines[0].removeprefix("# Notatka do artykułu: ") if first_lines else "?"
        print(f"  {note_file}")
        print(f"    Tytuł: {title[:80]}")
        print(f"    Plik:  {path}")
        print(f"    Claude: claude \"przeczytaj @{path} i dodaj do mojego Obsidian vault\"")
        print()


def main():
    print(f"article_browser v{__version__}")
    parser = argparse.ArgumentParser(
        description="Przeglądaj artykuły z Lenie DB i twórz notatki Obsidian")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="Lista artykułów")
    group.add_argument("--review", action="store_true", help="Interaktywny przegląd")
    group.add_argument("--show", action="store_true", help="Wyświetl artykuł i zakończ (wymaga --id)")
    group.add_argument("--notes", action="store_true", help="Pokaż zapisane notatki do przetworzenia")

    parser.add_argument("--since", default=None, help="Data od (YYYY-MM-DD)")
    parser.add_argument("--portal", default=None, help="Filtruj po portalu (np. onet.pl)")
    parser.add_argument("--state", default=None, help="Filtruj po stanie (np. MD_SIMPLIFIED)")
    parser.add_argument("--id", type=int, default=None, help="Zacznij od konkretnego ID")
    parser.add_argument("--view", action="store_true", help="Automatycznie pokaż treść przy --review")
    parser.add_argument("--check-urls", action="store_true", help="Sprawdź dostępność obrazków i linków")
    parser.add_argument("--limit", type=int, default=50, help="Maks. artykułów (domyślnie 50)")
    parser.add_argument("--format", choices=["table", "ids", "short"], default="table",
                        help="Format wyjścia --list: table (domyślnie), ids (same ID), short (ID + tytuł)")
    parser.add_argument("--not-reviewed", action="store_true", help="Tylko nieprzejrzane artykuły (reviewed_at IS NULL)")
    parser.add_argument("--no-obsidian", action="store_true", help="Tylko bez notatek Obsidian (obsidian_note_paths = [])")
    parser.add_argument("--not-cleaned", action="store_true", help="Tylko nieoczyszczone artykuły, które da się jeszcze przetworzyć automatycznie (regexp + LLM). Pomija NEED_MANUAL_REVIEW — dla tych użyj --manual-review")
    parser.add_argument("--manual-review", action="store_true", help="Wolny flow: tylko artykuły w stanie NEED_MANUAL_REVIEW (skrót do --state NEED_MANUAL_REVIEW)")
    args = parser.parse_args()

    # --manual-review to wygodny skrót do --state NEED_MANUAL_REVIEW
    if args.manual_review:
        if args.state and args.state != StalkerDocumentStatus.NEED_MANUAL_REVIEW.name:
            parser.error("--manual-review nie może być użyte razem z innym --state")
        args.state = StalkerDocumentStatus.NEED_MANUAL_REVIEW.name

    if args.notes:
        cmd_notes()
        return

    session = get_session()

    try:
        if args.show:
            cmd_show(session, article_id=args.id, check_urls=args.check_urls)
        elif args.list:
            cmd_list(session, since=args.since, portal=args.portal,
                     state=args.state, limit=args.limit, fmt=args.format,
                     not_reviewed=args.not_reviewed, no_obsidian=args.no_obsidian,
                     not_cleaned=args.not_cleaned)
        elif args.review:
            # Rozgrzej serwis NER w tle — ładowanie modelu spaCy (~90 s po
            # restarcie kontenera) nakłada się na przeglądanie artykułów,
            # zamiast blokować pierwszą akcję [w]/[e]
            from library.ner_client import warmup_async
            warmup_async()
            cmd_review(session, since=args.since, portal=args.portal,
                       start_id=args.id, limit=args.limit, auto_view=args.view,
                       check_urls=args.check_urls,
                       not_reviewed=args.not_reviewed, no_obsidian=args.no_obsidian,
                       not_cleaned=args.not_cleaned)
    finally:
        session.close()


if __name__ == "__main__":
    main()
