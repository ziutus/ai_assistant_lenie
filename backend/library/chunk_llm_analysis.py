"""LLM-based chunk analysis: rewrite (transcript correction) + summarize.

Extracted from the YouTube batch analysis CLI (now imports/youtube_batch_analyze.py)
for use by Flask API endpoints.
Supports Sherlock (Bielik) and ArkLabs models.
"""

import json
import logging
import re

logger = logging.getLogger(__name__)

REWRITE_MAX_TOKENS = 2_500
REWRITE_MIN_RATIO = 0.80
SUMMARY_MAX_TOKENS = 400
PRECLEAN_MAX_TOKENS = 1_200

SECTION_HEADER_RE = re.compile(r"^### (REKLAMA|TEMAT|SZUM): ?(.+)$", re.MULTILINE)

_ARKLABS_PREFIX = "arklabs/"

# Filler patterns: unambiguous hesitation sounds in Polish STT output
_FILLER_SOUND_RE = re.compile(
    r"\b(y{2,}|e{2,}|m{3,}|a{3,})\b",  # yyy, eee, mmm, aaaa
    re.IGNORECASE,
)
_STANDALONE_Y_RE = re.compile(r"(?<!\w)y(?!\w)", re.IGNORECASE)
_WORD_REPEAT_RE = re.compile(r"\b(\w+)\s+\1\b", re.IGNORECASE)


def _parse_cleanup_ranges(raw: str, line_count: int) -> list[dict]:
    """Parse and clamp line-range cleanup decisions returned by the LLM."""
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if not match:
        return []
    try:
        rows = json.loads(match.group())
    except (TypeError, ValueError):
        return []
    result = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or row.get("type") not in {"REKLAMA", "SZUM"}:
            continue
        try:
            start = max(1, min(line_count, int(row["start_line"])))
            end = max(start, min(line_count, int(row["end_line"])))
        except (KeyError, TypeError, ValueError):
            continue
        result.append({
            "start_line": start, "end_line": end, "type": row["type"],
            "reason": str(row.get("reason") or "Treść niemerytoryczna")[:500],
        })
    return result


def propose_article_cleanup(text: str, model: str, max_chars: int = 12_000) -> list[dict]:
    """Return a lossless TEMAT/REKLAMA/SZUM partition before final chunking.

    The model only identifies exact numbered line ranges. Original text is never
    rewritten, and anything not explicitly rejected remains TEMAT.
    """
    lines = text.splitlines()
    if not lines:
        return []
    labels = [("TEMAT", "Treść merytoryczna") for _ in lines]
    batch_start = 0
    while batch_start < len(lines):
        batch_end = batch_start
        size = 0
        while batch_end < len(lines) and (batch_end == batch_start or size + len(lines[batch_end]) + 12 <= max_chars):
            size += len(lines[batch_end]) + 12
            batch_end += 1
        numbered = "\n".join(f"{i - batch_start + 1}: {lines[i]}" for i in range(batch_start, batch_end))
        prompt = f"""Oceń linie surowego artykułu PRZED jego podziałem na fragmenty.
Wskaż wyłącznie zakresy, które należy wykluczyć:
- REKLAMA: sponsor, afiliacja, autopromocja, newsletter lub CTA,
- SZUM: menu, stopka, cookies, nawigacja, lista linków, podpis techniczny.
Nie oznaczaj jako szum nagłówków ani krótkich merytorycznych akapitów.
Zwróć TYLKO JSON: [{{"start_line": 2, "end_line": 4, "type": "SZUM", "reason": "lista linków"}}].
Gdy nic nie trzeba wykluczyć, zwróć [].

--- PONUMEROWANE LINIE ---
{numbered}
--- KONIEC ---"""
        raw, _ = call_model(prompt, model, PRECLEAN_MAX_TOKENS)
        for decision in _parse_cleanup_ranges(raw, batch_end - batch_start):
            for local_idx in range(decision["start_line"] - 1, decision["end_line"]):
                labels[batch_start + local_idx] = (decision["type"], decision["reason"])
        batch_start = batch_end

    pieces: list[dict] = []
    start = 0
    for i in range(1, len(lines) + 1):
        if i == len(lines) or labels[i] != labels[start]:
            piece_text = "\n".join(lines[start:i]).strip()
            if piece_text:
                pieces.append({"type": labels[start][0], "topic": labels[start][1], "text": piece_text})
            start = i
    return pieces


def extract_speaker_info(intro_text: str, model: str) -> list[dict]:
    """Ask LLM to identify speakers from the transcript introduction.

    Returns list of dicts: [{"name": "...", "role": "...", "description": "..."}]
    Returns [] if extraction fails or no speakers found.
    """
    prompt = f"""Z poniższego fragmentu transkrypcji podcastu wyekstrahuj informacje o rozmówcach.
Zwróć TYLKO tablicę JSON bez żadnego dodatkowego tekstu, w formacie:
[{{"name": "Imię Nazwisko", "role": "prowadzący", "description": "krótki opis stanowiska/roli"}}]

Jeśli nie możesz zidentyfikować rozmówców, zwróć pustą tablicę: []

Fragment transkrypcji:
{intro_text}"""

    logger.info("extract_speaker_info: len=%d", len(intro_text))
    response_text, _ = call_model(prompt, model, max_tokens=300)
    try:
        match = re.search(r'\[.*\]', response_text, re.DOTALL)
        if match:
            result = json.loads(match.group())
            if result and isinstance(result[0], list):
                result = result[0]
            return [sp for sp in result if isinstance(sp, dict)]
    except Exception:
        logger.warning("extract_speaker_info: failed to parse JSON response")
    return []


def head_tail_excerpt(text: str, chars: int = 1500) -> str:
    """First and last `chars` characters of text — a byline can appear at either end."""
    text = text.strip()
    if len(text) <= chars * 2:
        return text
    return text[:chars] + "\n...\n" + text[-chars:]


def extract_author_info(text: str, model: str) -> str | None:
    """Ask LLM to identify the article's author (byline) from a text excerpt.

    Returns the author's name, or None if extraction fails or no author found.
    """
    prompt = f"""Z poniższego fragmentu artykułu spróbuj ustalić imię i nazwisko autora (dziennikarza, publicysty).
Zwróć TYLKO obiekt JSON bez żadnego dodatkowego tekstu, w formacie:
{{"author": "Imię Nazwisko"}}

Jeśli nie możesz jednoznacznie zidentyfikować autora, zwróć: {{"author": null}}

Fragment artykułu:
{text}"""

    logger.info("extract_author_info: len=%d", len(text))
    response_text, _ = call_model(prompt, model, max_tokens=100)
    try:
        match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if match:
            result = json.loads(match.group())
            author = result.get("author")
            if isinstance(author, str) and author.strip():
                return author.strip()
    except Exception:
        logger.warning("extract_author_info: failed to parse JSON response")
    return None


def assign_speakers(text: str, speaker1: str, speaker2: str) -> str:
    """Parse >> speaker-change markers from YouTube auto-transcript and label each turn.

    YouTube inserts >> when it detects a speaker change. The first segment belongs to
    speaker1 (the host / first voice), then speakers alternate.
    Short segments (< 10 chars) that are just acknowledgments are still labeled.
    """
    segments = re.split(r"\s*>>\s*", text)
    speakers = [speaker1, speaker2]
    labeled = []
    for i, seg in enumerate(segments):
        seg = seg.strip()
        if not seg:
            continue
        label = speakers[i % 2]
        labeled.append(f"[{label}]: {seg}")
    return "\n\n".join(labeled)


def remove_speech_fillers(text: str) -> str:
    """Remove hesitation sounds and word repetitions from Polish STT transcript.

    Handles: yyy/eee/mmm (unambiguous sounds), standalone 'y', doubled words.
    Does NOT touch meaningful words — cheaper and more reliable than asking the LLM.
    """
    text = _FILLER_SOUND_RE.sub("", text)
    text = _STANDALONE_Y_RE.sub("", text)
    text = _WORD_REPEAT_RE.sub(r"\1", text)
    # Collapse multiple spaces left after removal
    text = re.sub(r" {2,}", " ", text)
    text = re.sub(r" ([,.\?!])", r"\1", text)  # fix space before punctuation
    return text.strip()


def call_model(prompt: str, model: str, max_tokens: int) -> tuple[str, int]:
    """Call the appropriate LLM backend and return (response_text, token_count)."""
    if model.startswith(_ARKLABS_PREFIX):
        from library.api.arklabs.arklabs_completion import arklabs_get_completion
        actual = f"speakleash/{model.removeprefix(_ARKLABS_PREFIX)}"
        result = arklabs_get_completion(prompt, model=actual, max_tokens=max_tokens, temperature=0.2)
    else:
        from library.api.cloudferro.sherlock.sherlock import sherlock_get_completion
        result = sherlock_get_completion(prompt, model=model, max_tokens=max_tokens, temperature=0.2)
    tokens = getattr(result, "prompt_tokens", 0) or 0
    return result.response_text, tokens


def rewrite_chunk_text(text: str, model: str, position: int = 1, total: int = 1,
                       prev_context: str = "", next_context: str = "") -> tuple[str, int]:
    """Pass 1: label section + correct transcript verbatim.

    Applies remove_speech_fillers() before sending to LLM — faster and cheaper than
    asking the model to do it.
    prev_context / next_context: boundary sentences from adjacent chunks — shown to the
    model as read-only context to improve coherence at chunk boundaries, not reproduced.
    Returns (best_response_text, rewrite_ratio_pct).
    Retries once if output < REWRITE_MIN_RATIO of input length, keeps the longer result.
    """
    text = remove_speech_fillers(text)
    ctx_prev = (
        f"\n[KONTEKST — koniec poprzedniego fragmentu, NIE przepisuj tego]:\n{prev_context}\n"
        if prev_context else ""
    )
    ctx_next = (
        f"\n[KONTEKST — początek następnego fragmentu, NIE przepisuj tego]:\n{next_context}\n"
        if next_context else ""
    )
    prompt = f"""Fragment {position}/{total} surowej transkrypcji podcastu YouTube.
{ctx_prev}Wykonaj DWIE rzeczy — nic więcej:

1. W PIERWSZEJ LINII wpisz etykietę sekcji (tylko jedną z dwóch opcji):
   ### REKLAMA: nazwa_sponsora      (gdy to blok reklamowy lub sponsorski)
   ### TEMAT: opis_3_4_słowa        (gdy to merytoryczna treść rozmowy)

2. Przepisz poniższy tekst DOSŁOWNIE — każde słowo musi zostać zachowane. Popraw tylko:
   - Interpunkcję i podział na zdania.
   - Oczywiste błędy transkrypcji (zamienione lub zlepione wyrazy).
   - Zachowaj etykiety [Mówca]: na początku każdej wypowiedzi — nie usuwaj ich.
   NIE skracaj. NIE streszczaj. NIE pomijaj żadnej informacji.

--- FRAGMENT DO PRZEPISANIA ---
{text}
--- KONIEC FRAGMENTU ---
{ctx_next}"""

    best = ""
    for attempt in range(1, 3):
        logger.info("rewrite chunk %d/%d, attempt %d, len=%d", position, total, attempt, len(text))
        response_text, tokens = call_model(prompt, model, REWRITE_MAX_TOKENS)
        logger.info("rewrite done: %d chars, %d tokens", len(response_text), tokens)
        if len(response_text) > len(best):
            best = response_text
        if len(response_text) >= len(text) * REWRITE_MIN_RATIO:
            break
        ratio_pct = round(len(response_text) / max(len(text), 1) * 100)
        logger.warning("rewrite too short (%d%% < %d%%), retrying", ratio_pct, round(REWRITE_MIN_RATIO * 100))

    ratio_pct = round(len(best) / max(len(text), 1) * 100)
    return best, ratio_pct


def summarize_chunk_text(corrected_text: str, model: str,
                         speakers: list[dict] | None = None) -> str:
    """Pass 2: summarize already-corrected text in 2-3 sentences.

    If speakers list is provided, the prompt includes participant names so the
    summary can use real names instead of generic 'Rozmówca'.
    """
    speakers_ctx = ""
    if speakers:
        names = ", ".join(
            f"{sp['name']}" + (f" ({sp.get('role', '')})" if sp.get("role") else "")
            for sp in speakers
        )
        speakers_ctx = f"Uczestnicy rozmowy: {names}.\n"

    prompt = f"""{speakers_ctx}Napisz streszczenie poniższego fragmentu merytorycznej rozmowy w 2-3 zdaniach.
Skup się na głównych tezach i wnioskach. Używaj imion rozmówców (nie pisz „Rozmówca"). Odpowiedz po polsku.

--- TEKST ---
{corrected_text}
--- KONIEC ---"""

    logger.info("summarize chunk, len=%d, speakers=%d", len(corrected_text), len(speakers or []))
    response_text, tokens = call_model(prompt, model, SUMMARY_MAX_TOKENS)
    logger.info("summarize done: %d tokens", tokens)
    return response_text.strip()


def parse_rewritten_chunk(raw: str) -> tuple[str, str, str]:
    """Extract (section_type, topic, corrected_text) from rewrite LLM output."""
    header_match = SECTION_HEADER_RE.search(raw)
    section_type = header_match.group(1) if header_match else "TEMAT"
    topic = header_match.group(2).strip() if header_match else ""
    text = raw[header_match.end():].strip() if header_match else raw.strip()
    return section_type, topic, text


def analyze_chunk_semantic(corrected_text: str, model: str,
                           speakers: list[dict] | None = None) -> dict:
    """Semantic-only re-analysis: classify + summarize already-corrected text.

    Skips the verbatim rewrite step. Use when corrected_text is already good
    and only type/topic/summary need to be refreshed.
    Returns dict with corrected_text unchanged.
    """
    speakers_ctx = ""
    if speakers:
        names = ", ".join(
            f"{sp['name']}" + (f" ({sp.get('role', '')})" if sp.get("role") else "")
            for sp in speakers
        )
        speakers_ctx = f"Uczestnicy rozmowy: {names}.\n"

    prompt = f"""{speakers_ctx}Sklasyfikuj poniższy fragment i jeśli to TEMAT — napisz streszczenie.

W PIERWSZEJ LINII wpisz etykietę (tylko jedną z dwóch opcji):
   ### REKLAMA: nazwa_sponsora      (blok reklamowy lub sponsorski)
   ### TEMAT: opis_3_4_słowa        (merytoryczna treść rozmowy)

Jeśli TEMAT: w kolejnych liniach napisz streszczenie w 2-3 zdaniach po polsku.
Używaj imion rozmówców (nie pisz „Rozmówca").
Jeśli REKLAMA: nie dodawaj nic więcej.

--- TEKST ---
{corrected_text}
--- KONIEC ---"""

    logger.info("semantic analysis, len=%d, speakers=%d", len(corrected_text), len(speakers or []))
    raw, tokens = call_model(prompt, model, SUMMARY_MAX_TOKENS)
    logger.info("semantic done: %d tokens", tokens)

    section_type, topic, summary_text = parse_rewritten_chunk(raw)
    return {
        "type": section_type,
        "topic": topic,
        "corrected_text": corrected_text,
        "summary": summary_text.strip() if section_type == "TEMAT" and summary_text.strip() else None,
        "rewrite_ratio": None,
    }


def analyze_article_chunk(original_text: str, model: str,
                          position: int = 1, total: int = 1) -> dict:
    """Analyze a chunk of a clean article/document — no verbatim rewrite.

    Article text is already clean (no STT artifacts), so a single LLM call
    classifies the chunk and summarizes it. Returns the same dict shape as
    analyze_chunk(), with corrected_text=None and rewrite_ratio=None.
    """
    prompt = f"""Fragment {position}/{total} artykułu lub dokumentu.

Sklasyfikuj poniższy fragment i jeśli to TEMAT — napisz streszczenie.

W PIERWSZEJ LINII wpisz etykietę (tylko jedną z trzech opcji):
   ### TEMAT: <temat>        (merytoryczna treść dokumentu)
   ### REKLAMA: <opis>       (treść reklamowa lub sponsorska)
   ### SZUM: <opis>          (szum techniczny strony: nawigacja portalu, menu, stopka,
                              cookie/zgody, listy linków "przeczytaj też", przyciski udostępniania)
W miejsce <temat>/<opis> wpisz KONKRETNY temat tego fragmentu w 3-5 słowach —
nie przepisuj dosłownie tekstu "<temat>" ani nazwy etykiety.
Jeśli fragment miesza szum z treścią merytoryczną — wybierz TEMAT.

Jeśli TEMAT: w kolejnych liniach napisz streszczenie w 2-3 zdaniach po polsku,
skupiając się na głównych tezach i wnioskach.
Jeśli REKLAMA lub SZUM: nie dodawaj nic więcej.

--- TEKST ---
{original_text}
--- KONIEC ---"""

    logger.info("article analysis chunk %d/%d, len=%d", position, total, len(original_text))
    raw, tokens = call_model(prompt, model, SUMMARY_MAX_TOKENS)
    logger.info("article analysis done: %d tokens", tokens)

    section_type, topic, summary_text = parse_rewritten_chunk(raw)
    # Bielik tends to prefix the summary with a literal "Streszczenie:" label
    summary_text = re.sub(r'^\s*Streszczenie:?\s*', '', summary_text, flags=re.IGNORECASE)
    return {
        "type": section_type,
        "topic": topic,
        "corrected_text": None,
        "summary": summary_text.strip() if section_type == "TEMAT" and summary_text.strip() else None,
        "rewrite_ratio": None,
    }


def analyze_chunk(original_text: str, model: str,
                  position: int = 1, total: int = 1,
                  speakers: list[dict] | None = None,
                  prev_context: str = "", next_context: str = "") -> dict:
    """Run full analysis pipeline on a single chunk.

    Returns dict:
        type          — "TEMAT" | "REKLAMA"
        topic         — short topic label from LLM
        corrected_text — rewritten transcript
        summary        — 2-3 sentence summary (None for REKLAMA)
        rewrite_ratio  — % of corrected vs original length
    """
    raw_rewrite, ratio = rewrite_chunk_text(original_text, model, position, total,
                                            prev_context=prev_context, next_context=next_context)
    section_type, topic, corrected_text = parse_rewritten_chunk(raw_rewrite)

    summary = None
    if section_type == "TEMAT":
        summary = summarize_chunk_text(corrected_text or original_text, model, speakers=speakers)

    return {
        "type": section_type,
        "topic": topic,
        "corrected_text": corrected_text,
        "summary": summary,
        "rewrite_ratio": ratio,
    }
