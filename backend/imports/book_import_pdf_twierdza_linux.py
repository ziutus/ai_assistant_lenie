"""CLI wrapper for importing the book "Twierdza Linux. Bezpieczeństwo dla
dociekliwych" into a Document (thin — all logic lives in
library/book_pdf_import.py so the same code can later run from a worker/job
instead of a developer machine, per
docs/deployment/nas/storage-and-jobs-migration-plan.md).

Every book needs its own thin script like this one: the shared engine in
library/book_pdf_import.py is parameterized (chapter regex, subheading
font/size, front/back-matter section titles, inline-style/table detection),
but there's no universal PDF signal for any of these — each book's layout
needs its own tuned values, hardcoded below as this book's defaults (still
overridable via CLI for one-off experiments). A different book gets its own
imports/book_import_pdf_<slug>.py with its own constants, built on the same
library functions.

Run imports/check_pdf_text_layer.py first — this script assumes the PDF has a
usable text layer (no OCR step).

Data access: ORM (SQLAlchemy) via get_session(), only when --apply is passed.

Running:
    cd backend
    python imports/book_import_pdf_twierdza_linux.py book.pdf                    # dry-run
    python imports/book_import_pdf_twierdza_linux.py book.pdf --apply            # writes
    python imports/book_import_pdf_twierdza_linux.py book.pdf --show 3
"""

import argparse
import sys

from library.book_pdf_import import (
    DEFAULT_CHAPTER_REGEX,
    apply_inline_styles,
    build_book_markdown,
    detect_heading_texts,
    detect_named_sections,
    extract_page_images,
    extract_pages,
    import_pdf_book,
    insert_page_tables,
)
from library.db.engine import get_session
from library.config_loader import load_config
from library.storage import storage_from_config
from library.upload_storage import get_uploaded_file

# This book's own values — see the module docstring above.
TITLE = "Twierdza Linux. Bezpieczeństwo dla dociekliwych"
BYLINE = "Karol Szafrański"
CHAPTER_REGEX = DEFAULT_CHAPTER_REGEX  # "// ROZDZIAŁ NNN //" running-head style (Sekurak)
HEADING_FONT_PREFIX = "BarlowCondensed"
HEADING_MIN_SIZE = 12.0

# Front/back-matter "part" sections with no numbered-chapter marker to regex
# against — detected instead by exact font/size + this explicit title
# allowlist (see library.book_pdf_import.detect_named_sections()). Two tiers
# observed in this book: an ALL-CAPS eyebrow running head (own page, own
# running head across the section) and a title-case opening title with no
# separate eyebrow. Both map the PDF's own exact text to the canonical title
# used as the "## " header, matching the printed spis treści's wording.
EXTRA_SECTION_EYEBROWS = {
    "OD AUTORA": "Od Autora",
    "OD WYDAWCY": "Od Wydawcy",
    "WSTĘP": "Wstęp Leszek Miś",
    "SŁOWNIK POJĘĆ": "Słownik pojęć",
    "ŹRÓDŁA WIEDZY": "Źródła wiedzy",
}
EXTRA_SECTION_TITLES = {
    "Podziękowania": "Podziękowania",
    "Linux Early Access: podziękowania": "Linux Early Access: podziękowania",
    "Konwencje stosowane w książce": "Konwencje stosowane w książce",
}
# Back-matter entries styled as an ordinary "### " subheading (same tier as
# detect_heading_texts()'s BarlowCondensed >=12pt) but printed as their own
# top-level spis treści line, not a subsection of something else — promoted
# to a real "## " chapter by exact already-marked heading text.
PROMOTE_SUBHEADINGS = {
    "SPIS TABEL": "Spis tabel",
    "SPIS RYSUNKÓW": "Spis rysunków",
    "BIBLIOGRAFIA": "Bibliografia",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", nargs="?", help="sciezka do lokalnego pliku PDF")
    parser.add_argument("--storage-key", help="klucz uploads/... zwrocony przez formularz uploadu")
    parser.add_argument("--title", default=TITLE, help="tytul ksiazki")
    parser.add_argument("--byline", default=BYLINE, help="autor")
    parser.add_argument("--source", default="own", help="zrodlo odkrycia (domyslnie 'own')")
    parser.add_argument("--url", default=None, help="synthetic url override (domyslnie file:///ksiazki/<slug>.pdf)")
    parser.add_argument("--chapter-regex", default=CHAPTER_REGEX, help="regex markera rozdzialu")
    parser.add_argument("--heading-font-prefix", default=HEADING_FONT_PREFIX, help="prefiks fontu podrozdzialow")
    parser.add_argument("--heading-min-size", type=float, default=HEADING_MIN_SIZE, help="min. rozmiar fontu podrozdzialow")
    parser.add_argument("--show", type=int, default=5, metavar="N", help="ile rozdzialow pokazac w podglada dry-run")
    parser.add_argument("--no-images", action="store_true", help="pomin ekstrakcje obrazow (domyslnie wlaczona)")
    parser.add_argument("--no-tables", action="store_true", help="pomin wykrywanie tabel (domyslnie wlaczone)")
    parser.add_argument("--no-styles", action="store_true", help="pomin inline code/kursywe (domyslnie wlaczone)")
    parser.add_argument("--no-extra-sections", action="store_true", help="pomin front/back-matter jako rozdzialy")
    parser.add_argument("--apply", action="store_true", help="zapisz do bazy (domyslnie dry-run)")
    args = parser.parse_args()
    if bool(args.file) == bool(args.storage_key):
        parser.error("podaj dokladnie jedno: lokalny plik albo --storage-key uploads/...")
    extract_images = not args.no_images
    detect_tables = not args.no_tables
    apply_styles = not args.no_styles
    extra_eyebrows = {} if args.no_extra_sections else EXTRA_SECTION_EYEBROWS
    extra_titles = {} if args.no_extra_sections else EXTRA_SECTION_TITLES
    promote_subheadings = {} if args.no_extra_sections else PROMOTE_SUBHEADINGS

    if args.storage_key:
        pdf_bytes = get_uploaded_file(storage_from_config(load_config()), args.storage_key)
        source_label = args.storage_key
    else:
        with open(args.file, "rb") as fh:
            pdf_bytes = fh.read()
        source_label = args.file

    if not args.apply:
        pages = extract_pages(pdf_bytes)
        if detect_tables:
            pages = insert_page_tables(pdf_bytes, pages)
        if apply_styles:
            pages = apply_inline_styles(pdf_bytes, pages)
        heading_texts = detect_heading_texts(
            pdf_bytes, font_prefix=args.heading_font_prefix, min_size=args.heading_min_size,
        )
        images = extract_page_images(pdf_bytes) if extract_images else []
        images_by_page: dict[int, list[int]] = {}
        for position, image in enumerate(images):
            images_by_page.setdefault(image.page_index, []).append(position)
        extra_sections = detect_named_sections(pdf_bytes, extra_eyebrows, extra_titles)
        result = build_book_markdown(
            pages, chapter_regex=args.chapter_regex, heading_texts=heading_texts, images_by_page=images_by_page,
            extra_sections=extra_sections, promote_subheadings=promote_subheadings,
        )
        print(f"Plik: {source_label}")
        print(f"Wykryto rozdzialow (laczna liczba ## ): {len(result.chapters)}")
        print(f"  w tym front/back-matter: {sum(len(v) for v in extra_sections.values()) + len(promote_subheadings)}")
        print(f"Wykryto podrozdzialow (### ): {len(heading_texts)}")
        print(f"Dlugosc markdown: {len(result.markdown)} znakow")
        print(f"Ramki info/ostrzezenie: {result.markdown.count('[!INFO]')} / {result.markdown.count('[!WARN]')}")
        print(f"Tabele (markdown): {result.markdown.count(chr(10) + '| ---')}")
        if extract_images:
            total_mb = sum(len(img.data) for img in images) / (1024 * 1024)
            print(f"Obrazy: {len(images)} wykrytych po filtrze, {total_mb:.1f} MB")
        print()
        for ch in result.chapters[: args.show]:
            print(f"  {ch.position:>3}. {ch.title} ({ch.length} zn.)")
        if len(result.chapters) > args.show:
            print(f"  ... i {len(result.chapters) - args.show} wiecej")
        print()
        print("Dry-run — nic nie zapisano. Uzyj --apply, aby utworzyc Document.")
        if not result.chapters:
            sys.exit(1)
        return

    session = get_session()
    try:
        doc, result = import_pdf_book(
            session,
            pdf_bytes,
            title=args.title,
            byline=args.byline,
            source=args.source,
            url=args.url,
            chapter_regex=args.chapter_regex,
            extract_images=extract_images,
            heading_font_prefix=args.heading_font_prefix,
            heading_min_size=args.heading_min_size,
            extra_section_eyebrows=extra_eyebrows,
            extra_section_titles=extra_titles,
            promote_subheadings=promote_subheadings,
            detect_tables=detect_tables,
            apply_styles=apply_styles,
        )
        print(f"Zapisano Document id={doc.id} uuid={doc.uuid}")
        print(f"Rozdzialow: {len(result.chapters)}, dlugosc markdown: {len(result.markdown)} znakow")
    finally:
        session.close()


if __name__ == "__main__":
    main()
