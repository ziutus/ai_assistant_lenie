"""CLI wrapper for importing a book PDF into a Document (thin — all logic lives in
library/book_pdf_import.py so the same code can later run from a worker/job instead
of a developer machine, per docs/deployment/nas/storage-and-jobs-migration-plan.md).

Run imports/check_pdf_text_layer.py first — this script assumes the PDF has a
usable text layer (no OCR step).

Data access: ORM (SQLAlchemy) via get_session(), only when --apply is passed.

Running:
    cd backend
    python imports/book_import_pdf.py book.pdf --title "..." --byline "..."               # dry-run
    python imports/book_import_pdf.py book.pdf --title "..." --byline "..." --apply       # writes
    python imports/book_import_pdf.py book.pdf --title "..." --chapter-regex "..." --show 3
"""

import argparse
import sys

from library.book_pdf_import import (
    DEFAULT_CHAPTER_REGEX,
    build_book_markdown,
    detect_heading_texts,
    extract_pages,
    import_pdf_book,
)
from library.db.engine import get_session


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", help="sciezka do pliku PDF")
    parser.add_argument("--title", required=True, help="tytul ksiazki")
    parser.add_argument("--byline", default=None, help="autor")
    parser.add_argument("--source", default="own", help="zrodlo odkrycia (domyslnie 'own')")
    parser.add_argument("--url", default=None, help="synthetic url override (domyslnie file:///ksiazki/<slug>.pdf)")
    parser.add_argument("--chapter-regex", default=DEFAULT_CHAPTER_REGEX, help="regex markera rozdzialu")
    parser.add_argument("--show", type=int, default=5, metavar="N", help="ile rozdzialow pokazac w podglada dry-run")
    parser.add_argument("--apply", action="store_true", help="zapisz do bazy (domyslnie dry-run)")
    args = parser.parse_args()

    with open(args.file, "rb") as fh:
        pdf_bytes = fh.read()

    if not args.apply:
        pages = extract_pages(pdf_bytes)
        heading_texts = detect_heading_texts(pdf_bytes)
        result = build_book_markdown(pages, chapter_regex=args.chapter_regex, heading_texts=heading_texts)
        print(f"Plik: {args.file}")
        print(f"Wykryto rozdzialow: {len(result.chapters)}")
        print(f"Wykryto podrozdzialow (### ): {len(heading_texts)}")
        print(f"Dlugosc markdown: {len(result.markdown)} znakow")
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
        )
        print(f"Zapisano Document id={doc.id} uuid={doc.uuid}")
        print(f"Rozdzialow: {len(result.chapters)}, dlugosc markdown: {len(result.markdown)} znakow")
    finally:
        session.close()


if __name__ == "__main__":
    main()
