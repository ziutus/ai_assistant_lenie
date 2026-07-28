"""Backfill document_references for doc 9339 ("Twierdza Linux") from the
book's own per-chapter endnote pages, https://twierdza.sekurak.pl/rN/.

Why this exists: unlike other Sekurak books imported so far,
imports/book_import_pdf_twierdza_linux.py's PDF text layer never carries
actual footnote body text — inline markers are a plain digit glued directly
onto the preceding word (e.g. "esej2"), and library/references.py's
extract_footnotes() (built for OCR books where the footnote text sits inline
on the scanned page) has nothing to extract for this book: doc 9339 has zero
document_references rows. The publisher instead publishes each chapter's
endnotes on its own page (r0 = "Wstęp Leszek Miś", r1..r13 = the 13 numbered
chapters, in book order) — see library/book_pdf_import.py's
fetch_chapter_footnotes() for the HTML shape.

The r0..r13 numbering has no signal left in text_md to key off directly
(build_book_markdown() strips each chapter's own "// ROZDZIAŁ N //" marker
down to plain title text) — so chapters are mapped by POSITION: walk
detect_chapters() in book order, skip every front/back-matter title (mirrors
book_import_pdf_twierdza_linux.py's EXTRA_SECTION_EYEBROWS/EXTRA_SECTION_TITLES/
PROMOTE_SUBHEADINGS — kept in sync manually, there are only a handful), and
number what's left 1, 2, 3... to match the site's own "Rozdział N" numbering.

Data access: ORM (SQLAlchemy) via get_session(), only when --apply is passed.
Network access: HTTP GET to twierdza.sekurak.pl, one request per chapter.
twierdza.sekurak.pl's Cloudflare front rate-limits/blocks some residential
IPs with an opaque 520 (confirmed from two unrelated networks on the same
day — not a plain site outage), so this script routes through the project's
existing Webshare rotating-residential proxy by default, same one
library.youtube_processing.py uses (WEBSHARE_API_KEY config) — pass
--no-proxy to fetch directly instead.

Running:
    cd backend
    python imports/book_twierdza_linux_fetch_references.py --id 9339              # dry-run
    python imports/book_twierdza_linux_fetch_references.py --id 9339 --apply
    python imports/book_twierdza_linux_fetch_references.py --id 9339 --no-proxy
"""

import argparse
import logging
import time

from library.book_pdf_import import fetch_chapter_footnotes
from library.config_loader import load_config
from library.db.engine import get_session
from library.references import save_chapter_references
from library.text_functions import detect_chapters

BASE_URL = "https://twierdza.sekurak.pl"

# Mirrors book_import_pdf_twierdza_linux.py's EXTRA_SECTION_EYEBROWS value for
# "WSTĘP" — the intro chapter is r0, not part of the r1.. numbered sequence.
INTRO_TITLE = "Wstęp Leszek Miś"

# Every other front/back-matter chapter title (mirrors
# book_import_pdf_twierdza_linux.py's EXTRA_SECTION_EYEBROWS/EXTRA_SECTION_TITLES/
# PROMOTE_SUBHEADINGS values, plus the printed "Spis treści" and the
# "(wstęp)" pseudo-chapter detect_chapters() may synthesize) — none of these
# have a source page of their own.
NON_NUMBERED_TITLES = {
    "Spis treści",
    "(wstęp)",
    "Od Autora",
    "Od Wydawcy",
    INTRO_TITLE,
    "Słownik pojęć",
    "Źródła wiedzy",
    "Podziękowania",
    "Linux Early Access: podziękowania",
    "Konwencje stosowane w książce",
    "Spis tabel",
    "Spis rysunków",
    "Bibliografia",
}


def map_chapters_to_source_urls(text: str) -> dict[int, tuple[str, str]]:
    """chapter_position (detect_chapters()) -> (source_url, chapter_title)."""
    mapping: dict[int, tuple[str, str]] = {}
    n = 1
    for ch in detect_chapters(text):
        title = ch["title"]
        if title == INTRO_TITLE:
            mapping[ch["position"]] = (f"{BASE_URL}/r0/", title)
        elif title not in NON_NUMBERED_TITLES:
            mapping[ch["position"]] = (f"{BASE_URL}/r{n}/", title)
            n += 1
    return mapping


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--id", type=int, required=True, help="document id (juz zaimportowana ksiazka)")
    parser.add_argument("--delay", type=float, default=0.5, help="opoznienie miedzy zadaniami HTTP, sekundy")
    parser.add_argument("--no-proxy", action="store_true", help="wylacz proxy Webshare, laczyc sie bezposrednio")
    parser.add_argument("--apply", action="store_true", help="zapisz do bazy (domyslnie dry-run)")
    args = parser.parse_args()

    proxies = None
    if not args.no_proxy:
        webshare_api_key = load_config().get("WEBSHARE_API_KEY")
        if webshare_api_key:
            from library.webshare_ip_auth import get_proxy_credentials

            creds = get_proxy_credentials(webshare_api_key)
            if creds:
                user, password = creds
                proxies = {
                    "http": f"http://{user}:{password}@p.webshare.io:80",
                    "https": f"http://{user}:{password}@p.webshare.io:80",
                }
                logging.info("Using Webshare rotating residential proxy")
            else:
                logging.warning("Could not fetch Webshare proxy credentials — proceeding without proxy")
        else:
            logging.info("No WEBSHARE_API_KEY configured — proceeding without proxy")

    session = get_session()
    try:
        from library.db.models import Document

        doc = session.get(Document, args.id)
        if doc is None:
            raise SystemExit(f"Brak dokumentu id={args.id}")

        mapping = map_chapters_to_source_urls(doc.text_md or "")
        if not mapping:
            raise SystemExit("Nie wykryto zadnych rozdzialow do zmapowania - sprawdz text_md dokumentu.")

        print(f"Dokument id={doc.id}: {doc.title}")
        print(f"Zmapowano {len(mapping)} rozdzialow na strony zrodel:\n")

        footnotes_by_chapter: dict[int, list[dict]] = {}
        total = 0
        for position, (url, title) in sorted(mapping.items()):
            footnotes = fetch_chapter_footnotes(url, proxies=proxies)
            print(f"  pozycja {position:>3} [{url}] {title}: {len(footnotes)} przypisow")
            if footnotes:
                footnotes_by_chapter[position] = footnotes
                total += len(footnotes)
            time.sleep(args.delay)

        print(f"\nLacznie znaleziono {total} przypisow w {len(footnotes_by_chapter)} rozdzialach.")

        if not args.apply:
            print("\nDry-run - nic nie zapisano. Uzyj --apply, aby zapisac document_references.")
            return

        save_chapter_references(session, doc, footnotes_by_chapter)
        session.commit()
        print(f"Zapisano document_references dla document id={doc.id}.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
