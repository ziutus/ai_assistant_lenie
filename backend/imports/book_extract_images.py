#!/usr/bin/env python3
"""Backfill: extract images from a book PDF already imported as a Document.

For books imported before image extraction existed (library/book_pdf_import.py
extract_images kwarg) — pulls illustrations straight out of the PDF and stores
them via ObjectStorage, without touching the document's existing text_md.

text_md is rebuilt from the PDF ONLY to recover each page's chapter position
(build_book_markdown() -> page_chapter_positions) — the result is discarded,
never written back. The document's real text_md may already have been edited
by extract_references.py (footnotes cut out); overwriting it here would lose
that work. For the same reason, this backfill never inserts [imgN] markers —
images land in the reader's collapsible "Ilustracje" section instead of
inline (see GET /document/<id>/chapter/<pos> "inline" flag).

Also uploads the source PDF to storage if it isn't there yet — books imported
while local storage writes to /app/data were silently failing (permissions)
never got their PDF saved at all.

Usage:
    cd backend
    python imports/book_extract_images.py --id 9332 --pdf "C:\\...\\twierdza-linux.pdf"           # dry-run
    python imports/book_extract_images.py --id 9332 --pdf "C:\\...\\twierdza-linux.pdf" --apply
"""

import argparse
import logging
import uuid as uuid_module
from collections import Counter

from library.config_loader import load_config

cfg = load_config()  # noqa: F841 — side effect: populates os.environ for library modules

from library.book_pdf_import import (  # noqa: E402
    DEFAULT_CHAPTER_REGEX,
    CONTENT_TYPE_BY_EXT,
    build_book_markdown,
    caption_for_page,
    detect_heading_texts,
    extract_page_images,
    extract_pages,
)
from library.db.engine import get_session  # noqa: E402
from library.db.models import Document  # noqa: E402
from library.document_images import replace_storage_images  # noqa: E402
from library.storage import storage_from_config  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Backfill images for an already-imported book PDF.")
    parser.add_argument("--id", type=int, required=True, help="Document id")
    parser.add_argument("--pdf", required=True, help="Path to the original PDF file")
    parser.add_argument("--chapter-regex", default=DEFAULT_CHAPTER_REGEX, help="Chapter marker regex")
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry-run)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    with open(args.pdf, "rb") as fh:
        pdf_bytes = fh.read()

    session = get_session()
    try:
        doc = session.get(Document, args.id)
        if doc is None:
            raise SystemExit(f"Document {args.id} not found")

        pages = extract_pages(pdf_bytes)
        heading_texts = detect_heading_texts(pdf_bytes)
        result = build_book_markdown(pages, chapter_regex=args.chapter_regex, heading_texts=heading_texts)

        images = extract_page_images(pdf_bytes)
        by_chapter = Counter(
            result.page_chapter_positions[img.page_index]
            if img.page_index < len(result.page_chapter_positions) else 0
            for img in images
        )
        total_mb = sum(len(img.data) for img in images) / (1024 * 1024)

        logging.info("Document %d: %s", doc.id, doc.title)
        logging.info("Wykryto obrazow po filtrze: %d, %.1f MB", len(images), total_mb)
        for chapter_position in sorted(by_chapter):
            label = "przed pierwszym rozdzialem" if chapter_position == 0 else f"rozdzial {chapter_position}"
            logging.info("  %s: %d", label, by_chapter[chapter_position])

        if not args.apply:
            logging.info("Dry-run — nic nie zapisano. Uzyj --apply, aby zapisac do storage/bazy.")
            return

        if not doc.uuid:
            doc.uuid = str(uuid_module.uuid4())
        pdf_uid = doc.uuid

        storage = storage_from_config(cfg)
        pdf_key = f"{pdf_uid}.pdf"
        if not storage.exists(pdf_key):
            storage.put_bytes(pdf_key, pdf_bytes, "application/pdf")
            logging.info("Zapisano PDF do storage: %s", pdf_key)
        else:
            logging.info("PDF juz jest w storage: %s", pdf_key)

        image_rows = []
        for position, page_image in enumerate(images):
            storage_key = f"documents/{pdf_uid}/images/{position}.{page_image.ext}"
            content_type = CONTENT_TYPE_BY_EXT.get(page_image.ext, "application/octet-stream")
            storage.put_bytes(storage_key, page_image.data, content_type)
            chapter_position = (
                result.page_chapter_positions[page_image.page_index]
                if page_image.page_index < len(result.page_chapter_positions) else 0
            )
            image_rows.append({
                "storage_key": storage_key,
                "position": None,  # backfill: no [imgN] marker in the existing text_md
                "page_number": page_image.page_index + 1,
                "chapter_position": chapter_position,
                "caption_text": caption_for_page(pages[page_image.page_index]),
            })
        rows = replace_storage_images(session, doc.id, image_rows)
        session.commit()
        logging.info("Zapisano %d wierszy document_images.", len(rows))
    finally:
        session.close()


if __name__ == "__main__":
    main()
