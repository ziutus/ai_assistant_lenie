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

Also strips the now-redundant inline footnote markers out of each chapter's
body text (see strip_inline_footnote_markers()) — this book's PDF text layer
never carried a real marker character, just a bare digit glued onto the
preceding word (e.g. "esej2"), which reads as a typo now that the real
footnote is shown separately. Per-chapter, all-or-nothing: only applied when
the count of markers actually stripped exactly matches that chapter's known
footnote count, otherwise the chapter's text is left untouched (reported).

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
import json
import logging
import re
import time

from library.ai import ai_ask
from library.book_pdf_import import fetch_chapter_footnotes
from library.config_loader import load_config
from library.db.engine import get_session
from library.references import save_chapter_references
from library.text_functions import detect_chapters

BASE_URL = "https://twierdza.sekurak.pl"
DEFAULT_MARKER_LLM_MODEL = "Bielik-11B-v3.0-Instruct"
# Safety cap on LLM calls per chapter (a chapter with this many *unresolved*
# gaps has bigger problems than this script can respect blindly — abort and
# report rather than keep spending calls).
MAX_LLM_CALLS_PER_CHAPTER = 20

# A footnote marker glued directly onto the end of the preceding word with no
# separating space and no true Unicode superscript (e.g. "esej2", "drugiej1")
# — see fetch_chapter_footnotes()'s docstring: the PDF text layer never
# carried a real marker character at all, this is the closest PyMuPDF's plain
# extraction gets. `(?<=[^\W\d])` requires a non-digit word char right before
# the digit run (never mid-number, e.g. "27001:2022"); `(?!\w)` requires
# nothing but a non-word char right after (never mid-identifier, e.g. the "4"
# in "log4j").
_INLINE_MARKER_SUFFIX_RE = re.compile(r"(?<=[^\W\d])(\d{1,3})(?!\w)")


def _parse_json_object(raw_response: str) -> dict | None:
    raw = (raw_response or "").strip()
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", raw, re.IGNORECASE | re.DOTALL)
    if fence:
        raw = fence.group(1).strip()
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


def _llm_locate_marker(window_text: str, marker: int, ref_text: str, model: str) -> dict | None:
    """Ask the LLM to find where footnote `marker`'s digit is hidden in
    window_text (a small span, NOT the whole chapter — see
    strip_inline_footnote_markers()) — used only when the plain regex/suffix
    match can't find it at all, e.g. the marker landed on a real number that
    already has its own space-separated digit ("NIS 2" + marker "6" ->
    "NIS 26", where "26" isn't even glued to a letter, so
    _INLINE_MARKER_SUFFIX_RE never sees it as a candidate).

    Returns {"original": exact verbatim substring, "cleaned": same substring
    with only the marker's digit removed} or None (LLM found nothing / gave
    an unusable answer). The caller MUST still verify `original` occurs
    exactly once in window_text before trusting it — this function applies
    nothing and does no verification of its own.
    """
    prompt = f"""Poniższy fragment książki technicznej pochodzi z tekstu wyodrębnionego z PDF-a. \
W oryginalnym PDF-ie w tym fragmencie występował numer przypisu {marker}, ale ekstrakcja tekstu \
zgubiła jego oddzielenie od reszty — przypis renderuje się jako zwykła cyfra doklejona BEZ SPACJI \
do końca poprzedzającego go słowa lub liczby (np. jakieś słowo zakończone od razu cyfrą numeru \
przypisu, albo liczba, po której bez spacji następuje numer przypisu).

WAŻNE: poniższy fragment może pochodzić z zupełnie innej części książki niż podany niżej przykład \
wzorca — nie zakładaj z góry, jakie słowo/liczba poprzedza numer przypisu, tylko przeszukaj \
DOSŁOWNIE podany fragment.

Treść przypisu {marker} (dla kontekstu, NIE wklejaj jej do odpowiedzi):
{ref_text[:300]}

Fragment tekstu:
{window_text}

Znajdź w powyższym fragmencie DOKŁADNE, dosłowne miejsce, gdzie cyfry "{marker}" oznaczają numer \
tego przypisu, doklejone bez spacji do poprzedzającego słowa lub liczby. Zwróć WYŁĄCZNIE JSON:
{{"found": true/false, "original": "dokładny fragment tekstu POWYŻEJ zawierający tę cyfrę \
(skopiowany 1:1 z fragmentu tekstu, tak krótki jak to możliwe, ale jednoznaczny)", "cleaned": "ten \
sam fragment, ale bez cyfr numeru przypisu {marker} (reszta identyczna co do znaku)"}}
Jeśli fragment tekstu NIE zawiera dosłownie cyfr "{marker}" doklejonych do żadnego słowa/liczby, \
zwróć dokładnie {{"found": false}} — nie zgaduj i nie kopiuj przykładów z tej instrukcji.
"""
    response = ai_ask(prompt, model=model, temperature=0.0, max_token_count=300, operation="footnote_marker_locate")
    payload = _parse_json_object(response.response_text)
    if not payload or not payload.get("found"):
        return None
    original, cleaned = payload.get("original"), payload.get("cleaned")
    if not isinstance(original, str) or not original or not isinstance(cleaned, str):
        return None
    return {"original": original, "cleaned": cleaned}

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


def _clean_chapter_markers(
    chapter_text: str, footnotes: list[dict], model: str, max_llm_calls: int,
) -> tuple[str, int, int]:
    """Strip one chapter's inline footnote markers 1..N (N = len(footnotes)),
    scanned strictly in reading order. Two tiers, cheapest first:

    1. _INLINE_MARKER_SUFFIX_RE candidates matching the expected marker
       EXACTLY as a whole number — no partial/suffix matching. An earlier
       version tried shrinking suffixes (so "NIS 26" could resolve to marker
       "6" glued onto "NIS 2") but that's provably unsafe: it also matched
       "7" out of a genuine two-digit marker "17" ("Atomic17"), silently
       corrupting it to "Atomic1". Any digit run that isn't an exact whole
       match is left completely alone here.
    2. When no regex candidate matches the currently-expected marker anywhere
       ahead, ask the LLM to locate it (_llm_locate_marker()) within a small
       bounded window — from the last successfully-stripped position up to
       the next regex candidate (whatever marker THAT turns out to be), not
       the rest of the chapter. This is where "NIS 26" gets resolved instead
       — the LLM has the footnote's own text as grounding ("NIS 2 Directive")
       to correctly split it, verified live before this was wired in. The
       LLM's answer is only ever trusted if its claimed "original" substring
       occurs in that window exactly once — otherwise this marker is left
       unresolved.

    Returns (new_text, stripped_count, llm_calls_used). stripped_count is
    compared against len(footnotes) by the caller — this function never
    decides on its own whether the result is "good enough" to keep.
    """
    footnote_text = {int(fn["marker"]): fn["text"] for fn in footnotes if fn.get("marker", "").isdigit()}
    total = len(footnotes)
    matches = list(_INLINE_MARKER_SUFFIX_RE.finditer(chapter_text))

    edits: list[tuple[int, int, str]] = []
    expected = 1
    match_idx = 0
    last_end = 0
    llm_calls = 0

    while expected <= total:
        found_idx = next(
            (i for i in range(match_idx, len(matches)) if int(matches[i].group(1)) == expected), None,
        )

        if found_idx is not None:
            m = matches[found_idx]
            edits.append((m.start(1), m.end(1), ""))
            last_end = m.end(1)
            match_idx = found_idx + 1
            expected += 1
            continue

        if llm_calls >= max_llm_calls:
            break
        window_end = matches[match_idx].start(1) if match_idx < len(matches) else len(chapter_text)
        window_text = chapter_text[last_end:window_end]
        llm_calls += 1
        result = _llm_locate_marker(window_text, expected, footnote_text.get(expected, ""), model)
        original = result["original"] if result else None
        if not original or window_text.count(original) != 1:
            break  # unresolved (not found, or ambiguous) — stop, caller sees a count mismatch
        rel_start = window_text.index(original)
        abs_start, abs_end = last_end + rel_start, last_end + rel_start + len(original)
        edits.append((abs_start, abs_end, result["cleaned"]))
        last_end = abs_end
        expected += 1

    pieces: list[str] = []
    cursor = 0
    for start, end, replacement in edits:
        pieces.append(chapter_text[cursor:start])
        pieces.append(replacement)
        cursor = end
    pieces.append(chapter_text[cursor:])
    return "".join(pieces), expected - 1, llm_calls


def strip_inline_footnote_markers(
    text: str, footnotes_by_chapter: dict[int, list[dict]], model: str = DEFAULT_MARKER_LLM_MODEL,
) -> tuple[str, list[dict]]:
    """Strip this book's inline footnote markers now that the real footnote
    text lives in document_references (save_chapter_references()) instead —
    see _clean_chapter_markers()/_INLINE_MARKER_SUFFIX_RE for the exact shape
    being matched and _llm_locate_marker() for the LLM-assisted fallback.

    A blind "strip any word's trailing digits" pass is NOT safe on a book
    this technical: SHA256, TPM2, ED25519, apache2, x86, IPv4 and dozens more
    are real trailing-digit terms that must never be touched. Instead, each
    chapter's markers are known (from how the publisher's own site numbers
    them) to appear in strict reading-order sequence 1, 2, 3, ... N — so only
    a digit run identified as the CURRENTLY EXPECTED next marker number is
    ever stripped, left to right; a real technical term's trailing digits
    essentially never land on the exact expected sequence position.

    Verified per chapter, not blindly trusted: if the number of markers
    actually stripped in a chapter doesn't exactly equal its real footnote
    count, that chapter is left completely untouched (its marker numbering
    can't be trusted) and reported as a mismatch — never a partial or silent
    corruption.

    footnotes_by_chapter maps a reader chapter_position (detect_chapters())
    to that chapter's already-fetched footnote dicts (from
    fetch_chapter_footnotes()) — both the count AND each marker's own
    reference text are used (the latter as LLM grounding). Returns
    (new_text, report) — report has one dict per chapter:
    {"position", "expected", "stripped", "ok", "llm_calls"}.
    """
    chapters = {ch["position"]: ch for ch in detect_chapters(text)}

    report: list[dict] = []
    pieces: list[str] = []
    cursor = 0
    for position in sorted(footnotes_by_chapter):
        ch = chapters.get(position)
        footnotes = footnotes_by_chapter[position]
        expected_total = len(footnotes)
        if ch is None or expected_total <= 0:
            continue
        pieces.append(text[cursor:ch["char_start"]])
        chapter_text = text[ch["char_start"]:ch["char_end"]]

        new_chapter_text, stripped, llm_calls = _clean_chapter_markers(
            chapter_text, footnotes, model, MAX_LLM_CALLS_PER_CHAPTER,
        )
        ok = stripped == expected_total
        report.append({
            "position": position, "expected": expected_total, "stripped": stripped,
            "ok": ok, "llm_calls": llm_calls,
        })
        pieces.append(new_chapter_text if ok else chapter_text)
        cursor = ch["char_end"]

    pieces.append(text[cursor:])
    return "".join(pieces), report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--id", type=int, required=True, help="document id (juz zaimportowana ksiazka)")
    parser.add_argument("--delay", type=float, default=0.5, help="opoznienie miedzy zadaniami HTTP, sekundy")
    parser.add_argument("--no-proxy", action="store_true", help="wylacz proxy Webshare, laczyc sie bezposrednio")
    parser.add_argument("--marker-model", default=DEFAULT_MARKER_LLM_MODEL, help="model LLM do lokalizowania ukrytych markerow przypisow")
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

        new_text, marker_report = strip_inline_footnote_markers(
            doc.text_md or "", footnotes_by_chapter, model=args.marker_model,
        )
        print("\nCzyszczenie inline markerow przypisow w tresci rozdzialow:")
        for row in marker_report:
            status = "OK" if row["ok"] else "POMINIETO (niezgodna liczba)"
            print(f"  pozycja {row['position']:>3}: oczekiwano {row['expected']:>3}, "
                  f"usunieto {row['stripped']:>3}, wywolan LLM {row['llm_calls']:>2}  [{status}]")
        mismatches = [row for row in marker_report if not row["ok"]]
        total_llm_calls = sum(row["llm_calls"] for row in marker_report)
        print(f"Laczna liczba wywolan LLM: {total_llm_calls}")

        if not args.apply:
            print("\nDry-run - nic nie zapisano. Uzyj --apply, aby zapisac document_references i wyczyszczony tekst.")
            return

        save_chapter_references(session, doc, footnotes_by_chapter)
        doc.text_md = new_text
        session.commit()
        print(f"Zapisano document_references i wyczyszczony text_md dla document id={doc.id}.")
        if mismatches:
            print(f"UWAGA: {len(mismatches)} rozdzialow pominieto przy czyszczeniu (patrz raport wyzej) — "
                  "ich tekst zostal bez zmian, przypisy nadal zapisane poprawnie.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
