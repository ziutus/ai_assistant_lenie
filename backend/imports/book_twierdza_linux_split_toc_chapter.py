#!/usr/bin/env python3
"""One-off, book-specific backfill for "Twierdza Linux" (doc 9339 on the NAS):
splits the printed "SPIS TREŚCI" page out of the "(wstęp)" pseudo-chapter into
its own real "## Spis treści" chapter, and strips the repeated "Spis treści"
running-head lines that print at the top of every following page of that
section (the printed TOC spans several pages; each one repeats "Spis treści"
as a page-top running head, same idea as the numbered chapters' own running
heads — just never marked/stripped at import time, since
book_import_pdf_twierdza_linux.py's EXTRA_SECTION_EYEBROWS explicitly
excludes "SPIS TREŚCI" to avoid it becoming an extra chapter — see that
script's docstring).

This is intentionally NOT a generic library feature: the running head
repeating in a DIFFERENT case ("SPIS TREŚCI" eyebrow once, then "Spis treści"
title-case on every later page) is this one book's own printed layout quirk,
not a pattern worth baking into library.book_pdf_import for every future
book. A pure text -> text transform either way — no PDF re-extraction needed.

Consequence this script accounts for: inserting a new chapter shifts every
later chapter's reader position by +1 (detect_chapters() numbers chapters by
"## " order, from scratch, on every read). document_images.chapter_position
is FIXED so images stay attached to the right chapter (recomputed from each
image's real "[imgN]" marker position in the NEW text, via detect_chapters()
— the same fresh-computation approach GET /document/<id>/anchor/<anchor_id>
uses, not a guessed shift). user_reading_progress rows are remapped by
matching each stored chapter TITLE (not position) between the old and new
chapter lists — current_chapter_title is exactly the snapshot the
UserReadingProgress model docstring says exists for this purpose. Tables
keyed by chapter_position that were empty for this document at the time of
writing (document_time_periods, document_tones, document_control_answers,
document_events, document_references, document_entities) are NOT migrated —
verify with fresh COUNT(*) queries before reusing this script on a document
where they aren't empty.

Usage:
    cd backend
    .venv/Scripts/python imports/book_twierdza_linux_split_toc_chapter.py --id 9339             # dry-run (default)
    .venv/Scripts/python imports/book_twierdza_linux_split_toc_chapter.py --id 9339 --apply
"""

import argparse
import logging
import re

from library.config_loader import load_config

cfg = load_config()  # noqa: F841 — side effect: populates os.environ for library modules

from library.db.engine import get_session  # noqa: E402
from library.db.models import Document, DocumentImage, UserReadingProgress  # noqa: E402
from library.text_functions import detect_chapters  # noqa: E402

logger = logging.getLogger(__name__)

# The printed TOC's own ALL-CAPS eyebrow line — appears exactly once, right
# before the first entry. Distinct from the title-case running head repeated
# on every later page of the section (_TOC_RUNNING_HEAD_LINE_RE below).
_TOC_EYEBROW_LINE_RE = re.compile(r"(?m)^SPIS TREŚCI$")
_TOC_RUNNING_HEAD_LINE_RE = re.compile(r"(?im)^Spis treści$")
_NEXT_HEADER_RE = re.compile(r"(?m)^## ")

# One-off correction for a data-quality bug from an EARLIER (unscoped)
# version of library.book_pdf_import.link_toc_entries(): before it scoped
# its subheading-recovery marking pass to stay outside the TOC's own page
# span, one already-applied run wrongly turned this specific TOC entry's own
# wrapped first line ("Tunelowanie połączeń do agenta SSH..." wraps across
# two printed lines, and only the second carries the dot leader — so
# _TOC_ENTRY_RE never matched the first line at all; it was instead read as
# a bare, unmatched paragraph by the region-based recovery path and happened
# to also match the real subheading's title elsewhere in the SSH chapter)
# into a real "### " header, with its own "[#toc-1]" anchor, sitting inside
# the printed TOC page rather than at the subheading's real body occurrence.
# Confirmed via the NAS DB before writing this: "anchor:toc-1)" is
# referenced by zero links, so removing it is safe — the data-integrity
# check below re-confirms that at run time rather than trusting this
# comment to still be true.
_STRAY_HEADER = "[#toc-1]\n\n### Tunelowanie połączeń do agenta SSH, czyli jak pracować wygodnie\n\n"
_STRAY_HEADER_FIXED = "Tunelowanie połączeń do agenta SSH, czyli jak pracować wygodnie\n\n"


def fix_stray_recovered_header(text: str) -> str:
    """Revert the one known stray "### " + anchor pair described above back
    to plain text. A no-op if the text doesn't contain that exact stray
    header (already fixed, or the bug never applied to this document).
    Raises if "toc-1" turns out to be referenced by a link after all — that
    would mean the assumption this fixup relies on no longer holds, and
    blindly deleting the anchor would leave a dangling link.
    """
    if _STRAY_HEADER not in text:
        return text
    if "anchor:toc-1)" in text:
        raise ValueError("toc-1 is referenced by a link — the known stray-header fixup no longer applies safely")
    return text.replace(_STRAY_HEADER, _STRAY_HEADER_FIXED, 1)


def split_toc_chapter(text: str) -> str:
    """Turn the first standalone "SPIS TREŚCI" line into a real "## Spis
    treści" chapter header, and drop every other standalone "Spis treści"
    line between it and the next real chapter header (the page-top running
    head repeated once per printed TOC page — pure layout noise, no
    information of its own). Raises ValueError if no such eyebrow line is
    found — this script assumes the exact printed convention this one book
    uses.
    """
    eyebrow = _TOC_EYEBROW_LINE_RE.search(text)
    if not eyebrow:
        raise ValueError("No standalone 'SPIS TREŚCI' eyebrow line found")
    next_header = _NEXT_HEADER_RE.search(text, eyebrow.end())
    region_end = next_header.start() if next_header else len(text)

    before = text[:eyebrow.start()]
    region = "## Spis treści" + text[eyebrow.end():region_end]
    after = text[region_end:]

    lines = [line for line in region.split("\n") if not _TOC_RUNNING_HEAD_LINE_RE.match(line.strip())]
    region = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))

    return before + region + after


def _chapter_at(chapters: list[dict], char_pos: int) -> dict | None:
    return next((c for c in chapters if c["char_start"] <= char_pos < c["char_end"]), None)


def main():
    parser = argparse.ArgumentParser(
        description="Book-specific backfill: split 'Twierdza Linux' SPIS TREŚCI into its own chapter."
    )
    parser.add_argument("--id", type=int, required=True, help="Document id (expected: 9339, 'Twierdza Linux')")
    parser.add_argument("--apply", action="store_true", help="Write changes to the database (default: dry-run)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    session = get_session()
    try:
        doc = session.get(Document, args.id)
        if doc is None:
            raise SystemExit(f"Document {args.id} not found")
        if not doc.text_md:
            raise SystemExit(f"Document {args.id} has no text_md")

        old_text = fix_stray_recovered_header(doc.text_md)
        old_chapters = detect_chapters(old_text)
        new_text = split_toc_chapter(old_text)
        new_chapters = detect_chapters(new_text)

        logging.info(
            "doc #%s: %d chapters -> %d chapters (old %d chars, new %d chars)",
            args.id, len(old_chapters), len(new_chapters), len(old_text), len(new_text),
        )
        for c in new_chapters[:6]:
            logging.info("  %2d. %s (%d chars)", c["position"], c["title"], c["length"])

        images = (
            session.query(DocumentImage)
            .filter(DocumentImage.document_id == args.id, DocumentImage.storage_key.isnot(None))
            .all()
        )
        image_updates: list[tuple[DocumentImage, int, int]] = []
        for img in images:
            if img.position is None:
                continue
            marker = f"[img{img.position}]"
            idx = new_text.find(marker)
            if idx == -1:
                logging.warning("  image position=%s: marker %s not found in new text — left untouched", img.position, marker)
                continue
            new_chapter = _chapter_at(new_chapters, idx)
            if new_chapter is None:
                logging.warning("  image position=%s: marker found but not inside any chapter", img.position)
                continue
            if new_chapter["position"] != img.chapter_position:
                image_updates.append((img, img.chapter_position, new_chapter["position"]))
        logging.info("images: %d total, %d need a chapter_position update", len(images), len(image_updates))
        for img, old_pos, new_pos in image_updates[:15]:
            logging.info("  image id=%s: chapter_position %s -> %s", img.id, old_pos, new_pos)
        if len(image_updates) > 15:
            logging.info("  ... and %d more", len(image_updates) - 15)

        progress_rows = (
            session.query(UserReadingProgress).filter(UserReadingProgress.document_id == args.id).all()
        )
        progress_updates: list[tuple[UserReadingProgress, int, int]] = []
        for row in progress_rows:
            old_chapter = next((c for c in old_chapters if c["position"] == row.current_chapter), None)
            title = old_chapter["title"] if old_chapter else row.current_chapter_title
            new_chapter = next((c for c in new_chapters if c["title"] == title), None)
            if new_chapter is None:
                logging.warning(
                    "  reading_progress id=%s: chapter title %r not found in new chapter list — left untouched",
                    row.id, title,
                )
                continue
            if new_chapter["position"] != row.current_chapter:
                progress_updates.append((row, row.current_chapter, new_chapter["position"]))
        logging.info(
            "reading progress: %d rows, %d need a current_chapter update", len(progress_rows), len(progress_updates)
        )
        for row, old_pos, new_pos in progress_updates:
            logging.info("  progress id=%s (user %s): current_chapter %s -> %s", row.id, row.user_id, old_pos, new_pos)

        if args.apply:
            doc.text_md = new_text
            for img, _old_pos, new_pos in image_updates:
                img.chapter_position = new_pos
            for row, _old_pos, new_pos in progress_updates:
                row.current_chapter = new_pos
            session.commit()
            logging.info("Saved.")
        else:
            logging.info("Dry-run — nothing written. Re-run with --apply to save.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
