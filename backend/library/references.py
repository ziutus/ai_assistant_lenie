"""Extract footnotes/references out of a book's text_md (document_references).

Mistral OCR leaves book footnotes inline where they fell on the scanned page:

    ¹⁸ https://www.statista.com/statistics/973952/... (dostęp: 12.09.2024).
    29 Eurostat.
    2 Art. 173 Konstytucji Rzeczpospolitej Polskiej (Dz.U. 1997, nr 78, poz.483).

They interrupt reading mid-paragraph and pollute downstream processing — NER
used to emit "person" entities like "¹¹ stat.gov.pl/obszary-tematyczne/...".
This module removes footnote lines from the text and returns them as
structured rows (marker, text, first URL, chapter position) for the
document_references table; the reader renders them as a per-chapter
"Przypisy" section instead.

Detection is conservative: superscript-marked lines are always footnotes;
digit-marked lines (1-99) need a bibliographic signal (URL, "(dostęp:",
a year, legal/citation phrases, or a short sentence ending with a period) so
narrative paragraphs that happen to start with a number stay untouched.
"""

import logging
import re

logger = logging.getLogger(__name__)

_SUP_TO_DIGIT = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")

_SUP_LINE_RE = re.compile(r"^([¹²³⁴⁵⁶⁷⁸⁹⁰]+)\s+(\S.*)$")
_NUM_LINE_RE = re.compile(r"^(\d{1,2})\s+(\S.*)$")

_URL_RE = re.compile(
    r"(https?://\S+|www\.\S+|\b[a-z0-9][a-z0-9.-]*\.[a-z]{2,}/\S+)", re.IGNORECASE,
)
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_CITATION_RE = re.compile(r"op\.\s*cit\.|Ibidem|Tamże|sygn\.\s*akt|Dz\.\s*U\.|\(dostęp:", re.IGNORECASE)

# Short bibliographic entries without other signals ("29 Eurostat.").
_MAX_SHORT_BIBLIO_CHARS = 120


def _is_numbered_footnote(content: str) -> bool:
    """Signals that a '<digits> <content>' line is a footnote, not narrative text."""
    if _URL_RE.match(content):
        return True  # starts with a URL/domain ("12 www.archiwum.nask.pl/...")
    if content[0].islower():
        return False  # narrative continuation; footnote sources start uppercase
    if _CITATION_RE.search(content) or _YEAR_RE.search(content):
        return True
    return len(content) <= _MAX_SHORT_BIBLIO_CHARS and content.endswith(".")


def _first_url(content: str) -> str | None:
    match = _URL_RE.search(content)
    if not match:
        return None
    url = match.group(1).rstrip(".,;)")
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url
    return url


def extract_footnotes(text: str) -> tuple[str, list[dict]]:
    """Split text into (clean text, footnotes).

    Each footnote: {"marker", "text", "url", "char_offset"} — char_offset is
    the line's position in the ORIGINAL text, so callers can assign chapters
    before the removal shifts offsets. Runs of blank lines left behind by
    removed footnotes collapse to one blank line.
    """
    footnotes: list[dict] = []
    kept: list[str] = []
    offset = 0
    for line in text.split("\n"):
        stripped = line.strip()
        marker = content = None
        match = _SUP_LINE_RE.match(stripped)
        if match:
            marker = match.group(1).translate(_SUP_TO_DIGIT)
            content = match.group(2).strip()
        else:
            match = _NUM_LINE_RE.match(stripped)
            if match and _is_numbered_footnote(match.group(2).strip()):
                marker, content = match.group(1), match.group(2).strip()
        if content:
            footnotes.append({
                "marker": marker,
                "text": content,
                "url": _first_url(content),
                "char_offset": offset,
            })
        else:
            kept.append(line)
        offset += len(line) + 1

    clean = re.sub(r"\n{3,}", "\n\n", "\n".join(kept))
    return clean, footnotes


def refresh_document_references(session, doc) -> list:
    """Extract footnotes from doc.text_md into document_references rows.

    Replace semantics per document (derived data, like document_entities).
    Assigns each footnote to its reader chapter (detect_chapters on the
    original text — headers are untouched, so positions stay valid after
    removal) and UPDATES doc.text_md to the cleaned text. Queues everything
    on the session without committing; no footnotes found = no changes.
    Returns the new DocumentReference rows.
    """
    from sqlalchemy import delete

    from library.db.models import DocumentReference
    from library.text_functions import detect_chapters

    text = doc.text_md or ""
    clean, footnotes = extract_footnotes(text)
    if not footnotes:
        return []

    chapters = detect_chapters(text)

    def _chapter_for(char_offset: int) -> int | None:
        for ch in chapters:
            if ch["char_start"] <= char_offset < ch["char_end"]:
                return ch["position"]
        return None

    session.execute(delete(DocumentReference).where(DocumentReference.document_id == doc.id))
    rows = [
        DocumentReference(
            document_id=doc.id,
            chapter_position=_chapter_for(fn["char_offset"]),
            marker=fn["marker"],
            ref_text=fn["text"],
            url=fn["url"],
        )
        for fn in footnotes
    ]
    session.add_all(rows)
    doc.text_md = clean
    logger.info("references doc=%s: extracted %d footnotes (%d chars -> %d)",
                doc.id, len(rows), len(text), len(clean))
    return rows
