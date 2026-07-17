"""Ocena staranności ("quality") artykułu + wykrywanie podpisów zdjęć.

Dwie warstwy:
- deterministyczne kary (bez LLM): podpisy zdjęć / stockowe credity, brak
  autora, udział REKLAMA/SZUM w analizowanym tekście, bardzo krótki tekst,
  clickbaitowy tytuł,
- rubryka LLM (jedno wywołanie): źródła / głębia / język, każdy wymiar 0-5.

Wynik (0-100, im wyżej tym staranniej) trafia do web_documents.quality (JSONB).
Wykrywanie podpisów zdjęć jest współdzielone z article_cleaner (usuwanie linii)
— jedna definicja wzorców dla czyszczenia i punktacji.
"""

import datetime
import json
import logging
import re
from collections import Counter

logger = logging.getLogger(__name__)

RUBRIC_MAX_TOKENS = 300
RUBRIC_INPUT_CHARS = 6_000
SHORT_TEXT_CHARS = 1_500

# Podpis zdjęcia to KRÓTKA linia — dłuższe akapity wspominające o fotografii
# to treść merytoryczna, nie credit.
_CAPTION_MAX_CHARS = 120

# Linie zaczynające się od typowego prefiksu creditu
_CAPTION_PREFIX_RE = re.compile(
    r"^\s*(?:\*{1,2}|_)?\s*(?:fot\.|foto:|zdj[eę]cie:|zdj\.|źród[łl]o\s+zdj[eę]cia|autor\s+zdj[eę]cia)",
    re.IGNORECASE,
)

# Sygnały stockowe/agencyjne w dowolnym miejscu krótkiej linii.
# Osobne wzorce są potrzebne do oceny pochodzenia zdjęć: fotografia
# agencyjna nie powinna dostawać tej samej kary co generyczny stock.
_CAPTION_STOCK_RE = re.compile(
    r"(?:shutterstock|getty\s*images?|east\s+news|adobe\s+stock|"
    r"istock(?:photo)?|depositphotos|123rf|unsplash|pexels)",
    re.IGNORECASE,
)

_CAPTION_AGENCY_SOURCE_RE = re.compile(
    r"(?:\bPAP\s*/|/\s*PAP\b|\bEPA\b|\bAFP\b|\bReuters\b|"
    r"\bForum\b\s*/|/\s*Forum\b)",
    re.IGNORECASE,
)

_CAPTION_AGENCY_RE = re.compile(
    r"(?:zdj[eę]cie\s+ilustracyjne|shutterstock|getty\s*images?|east\s+news|"
    r"adobe\s+stock|istock(?:photo)?|depositphotos|123rf|unsplash|pexels|"
    r"domena\s+publiczna|\bcc\s+by(?:-sa)?\b|creative\s+commons|archiwum\s+prywatne|©|"
    r"\bPAP\s*/|/\s*PAP\b|\bEPA\b|\bAFP\b|\bReuters\b|\bForum\b\s*/|/\s*Forum\b)",
    re.IGNORECASE,
)

# Punkty oznaczają jakość/oryginalność źródła, a nie fakt, że
# podpis pozostał w tekście. Materiał własny jest najlepszy, fotografia
# agencyjna jest pełnowartościowym źródłem redakcyjnym, a stock i zdjęcia
# czysto ilustracyjne dostają najwyższą karę. Limit całej kategorii: 15.
PHOTO_SOURCE_PENALTY_WEIGHTS = {
    "own_or_private_archive": 0,
    "agency": 1,
    "creative_commons": 2,
    "public_domain": 2,
    "stock": 3,
    "illustrative": 3,
    "image_credit": 2,
    "other": 2,
}

# Podpis bywa dłuższy niż _CAPTION_MAX_CHARS, ale linia KOŃCZĄCA SIĘ
# "(zdjęcie ilustracyjne)" to zawsze podpis, niezależnie od długości.
_CAPTION_SUFFIX_RE = re.compile(r"\((?:zdj[eę]cie|zdj\.)\s+ilustracyjne\)\s*$", re.IGNORECASE)

_CLICKBAIT_RE = re.compile(
    r"(?:nie uwierzysz|szok(?:uj[aą]c\w*)?\b|musisz to zobaczy[ćc]|zobacz,? co|"
    r"a[żz] trudno uwierzy[ćc]|to zmieni (?:tw[oó]j|wszystko)|jednym trikiem|"
    r"zdradzi[łl]a? sekret|internauci oszaleli|wszyscy o (?:tym|niej|nim) m[oó]wi[aą])",
    re.IGNORECASE,
)

_REFERENCES_HEADING_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:źródła|zrodla|bibliografia|references|literatura)\s*:?\s*$",
    re.IGNORECASE,
)


def is_references_section(text: str) -> bool:
    """True for a non-content chunk consisting of a references list.

    Such chunks are intentionally excluded from embeddings, but they are
    evidence of diligence and must not count as editorial noise.
    """
    from library.cited_publications import extract_cited_publications

    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    if not lines or not extract_cited_publications(text):
        return False
    return bool(_REFERENCES_HEADING_RE.match(lines[0]))


def is_photo_caption_line(line: str) -> bool:
    """Czy linia jest podpisem zdjęcia / creditem fotografa (np.
    "zdjęcie ilustracyjne, Dmytro Buiansky / shutterstock")?"""
    stripped = line.strip()
    if not stripped:
        return False
    if _CAPTION_SUFFIX_RE.search(stripped):
        return True
    if len(stripped) > _CAPTION_MAX_CHARS:
        return False
    # Usuń markery [imgN] — podpis często sąsiaduje z markerem obrazka
    bare = re.sub(r"\[img\d+(?::[^\]]*)?\]", "", stripped).strip()
    if not bare:
        return False
    return bool(_CAPTION_PREFIX_RE.match(bare) or _CAPTION_AGENCY_RE.search(bare))


def count_photo_captions(text: str) -> int:
    """Liczba linii-podpisów zdjęć w tekście (sygnał do oceny staranności)."""
    if not text:
        return 0
    return sum(1 for line in text.splitlines() if is_photo_caption_line(line))


def photo_caption_candidates(text: str) -> list[dict]:
    """Wykryte podpisy wraz z kategorią — dowody dla quality i podpowiedzi UI."""
    candidates = []
    pending_image_alt: str | None = None
    pending_image_lines = 0
    for index, line in enumerate((text or "").splitlines()):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("[img"):
            candidates.append({"line_index": index, "text": stripped, "category": "image_marker"})
            marker = re.match(r'^\[img\d+(?::\s*([^\]]*))?\]\s*$', stripped)
            pending_image_alt = (marker.group(1) or "").strip() if marker else None
            pending_image_lines = 3 if marker else 0
            if not marker:
                candidates.append({"line_index": index, "text": stripped, "category": "image_description"})
            continue

        direct_caption = is_photo_caption_line(stripped)
        normalized = re.sub(r'\s+', ' ', stripped).casefold()
        normalized_alt = re.sub(r'\s+', ' ', pending_image_alt or '').casefold()
        repeats_image_alt = bool(pending_image_alt and normalized == normalized_alt)
        adjacent_description = bool(
            pending_image_lines > 0 and not stripped.startswith("#")
            and (len(stripped) <= 120 or (repeats_image_alt and len(stripped) <= 300))
        )
        if pending_image_lines > 0:
            pending_image_lines -= 1
            if repeats_image_alt or (not direct_caption and not adjacent_description):
                pending_image_alt = None
                pending_image_lines = 0
        if not (direct_caption or adjacent_description):
            continue
        lowered = stripped.lower()
        if "domena publiczna" in lowered:
            category = "public_domain"
        elif re.search(r'\bcc\s+by(?:-sa)?\b|creative commons', lowered):
            category = "creative_commons"
        elif "archiwum prywatne" in lowered:
            category = "own_or_private_archive"
        elif re.search(r'zdj[eę]cie\s+ilustracyjne', lowered):
            category = "illustrative"
        elif _CAPTION_STOCK_RE.search(line):
            category = "stock"
        elif _CAPTION_AGENCY_SOURCE_RE.search(line):
            category = "agency"
        elif adjacent_description:
            category = "image_description" if repeats_image_alt else "image_credit"
        else:
            category = "other"
        candidates.append({"line_index": index, "text": line.strip(), "category": category})
    return candidates


def remove_photo_caption_lines(text: str) -> str:
    """Kopia tekstu bez podpisów zdjęć, przeznaczona dla embeddingów/search."""
    candidates = {item["line_index"] for item in photo_caption_candidates(text)}
    return "\n".join(
        line for index, line in enumerate((text or "").splitlines())
        if index not in candidates
    )


def is_clickbait_title(title: str | None) -> bool:
    return bool(title and _CLICKBAIT_RE.search(title))


def _llm_rubric(text: str, model: str, cited_publications: list[dict] | None = None) -> dict | None:
    """Jedno wywołanie LLM: oceny 0-5 w trzech wymiarach staranności.

    Zwraca {"zrodla": n, "glebia": n, "jezyk": n, "uzasadnienie": "..."}
    albo None, gdy wywołanie/parsowanie się nie powiedzie.
    """
    from library.chunk_llm_analysis import call_model

    citation_lines = []
    for item in cited_publications or []:
        identifier = item.get("pmid") or item.get("pmcid") or item.get("doi") or item.get("canonical_url")
        if identifier:
            citation_lines.append(f"- {identifier}: {item.get('raw_citation') or item.get('canonical_url') or ''}")
    citation_context = "\n".join(citation_lines) or "brak automatycznie rozpoznanych publikacji"

    prompt = f"""Oceń staranność poniższego artykułu w trzech wymiarach, każdy w skali 0-5:
- "zrodla": czy autor powołuje się na konkretne źródła (dokumenty, dane, ekspertów z nazwiska), czy tylko ogólniki typu "media donoszą",
- "glebia": czy tekst zawiera własną analizę i kontekst, czy jest przepisaną notką/depeszą,
- "jezyk": poprawność i staranność językowa.

Zwróć TYLKO obiekt JSON bez dodatkowego tekstu:
{{"zrodla": 0, "glebia": 0, "jezyk": 0, "uzasadnienie": "1-2 zdania"}}

--- ARTYKUŁ ---
{text[:RUBRIC_INPUT_CHARS]}
--- KONIEC ---

--- PUBLIKACJE ROZPOZNANE W SEKCJI ŹRÓDEŁ DOKUMENTU ---
{citation_context}
--- KONIEC PUBLIKACJI ---
Uwzględnij tę listę przy ocenie pola "zrodla", nawet jeśli została technicznie wydzielona poza tekst główny."""
    try:
        raw, _ = call_model(prompt, model, RUBRIC_MAX_TOKENS)
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return None
        data = json.loads(match.group())
        rubric = {}
        for key in ("zrodla", "glebia", "jezyk"):
            rubric[key] = max(0, min(5, int(data.get(key, 0))))
        rubric["uzasadnienie"] = str(data.get("uzasadnienie") or "")[:500]
        return rubric
    except Exception:
        logger.exception("LLM quality rubric failed")
        return None


def compute_quality(doc, chunk_sections: list[dict], model: str | None = None) -> dict:
    """Policz ocenę staranności dokumentu na podstawie chunków z analizy.

    chunk_sections: [{"type": "TEMAT|REKLAMA|SZUM", "original": "tekst"}, ...]
    model: model LLM do rubryki; None = tylko kary deterministyczne.

    Wynik: {"score": 0-100, "penalties": {...}, "signals": {...},
            "llm_rubric": {...}|None, "model": ..., "computed_at": ISO}
    """
    temat_text = "\n".join(
        (s.get("original") or "") for s in chunk_sections if s.get("type") == "TEMAT"
    )
    reference_sections = [
        s for s in chunk_sections
        if s.get("type") == "ZRODLA"
        or (s.get("type") != "TEMAT" and is_references_section(s.get("original") or ""))
    ]
    reference_len = sum(len(s.get("original") or "") for s in reference_sections)
    noise_len = sum(
        len(s.get("original") or "") for s in chunk_sections
        if s.get("type") != "TEMAT" and s not in reference_sections
    )
    total_len = len(temat_text) + noise_len + reference_len

    full_text = "\n".join((s.get("original") or "") for s in chunk_sections)
    from library.cited_publications import extract_cited_publications
    cited_publications = extract_cited_publications(full_text)
    caption_evidence = photo_caption_candidates(full_text)
    photo_source_evidence = [
        item for item in caption_evidence
        if item["category"] in PHOTO_SOURCE_PENALTY_WEIGHTS
    ]
    captions = len(photo_source_evidence)
    photo_source_penalty_details = Counter()
    for item in photo_source_evidence:
        weight = PHOTO_SOURCE_PENALTY_WEIGHTS[item["category"]]
        if weight:
            photo_source_penalty_details[item["category"]] += weight
    noise_share = (noise_len / total_len) if total_len else 0.0

    penalties: dict[str, int] = {}
    photo_source_penalty = min(15, sum(photo_source_penalty_details.values()))
    if photo_source_penalty:
        penalties["photo_sources"] = photo_source_penalty
    if not (getattr(doc, "author", None) or "").strip():
        penalties["missing_author"] = 10
    if noise_share > 0:
        penalties["noise_share"] = min(20, round(noise_share * 50))
    if len(temat_text.strip()) < SHORT_TEXT_CHARS:
        penalties["short_text"] = 10
    if is_clickbait_title(getattr(doc, "title", None)):
        penalties["clickbait_title"] = 5

    rubric = None
    if model and temat_text.strip():
        rubric = _llm_rubric(temat_text, model, cited_publications)
        if rubric:
            # Structured identifiers are grounded evidence, not an LLM guess.
            # Prevent a separated references chunk from being scored as "no
            # sources" merely because the rubric sees TEMAT prose separately.
            citation_floor = 4 if len(cited_publications) >= 3 else 3 if len(cited_publications) == 2 else 2 if cited_publications else 0
            rubric["zrodla"] = max(rubric["zrodla"], citation_floor)
            rubric_sum = rubric["zrodla"] + rubric["glebia"] + rubric["jezyk"]
            penalties["llm_rubric"] = (15 - rubric_sum) * 2  # 0-30

    score = max(0, 100 - sum(penalties.values()))
    return {
        "score": score,
        "penalties": penalties,
        "signals": {
            "photo_captions": captions,
            "photo_caption_categories": dict(Counter(item["category"] for item in photo_source_evidence)),
            "photo_caption_lines": [item["text"] for item in photo_source_evidence[:20]],
            "photo_source_penalty_details": dict(photo_source_penalty_details),
            "noise_share": round(noise_share, 3),
            "reference_chars": reference_len,
            "temat_chars": len(temat_text),
            "cited_publications": len(cited_publications),
        },
        "llm_rubric": rubric,
        "model": model if rubric else None,
        "computed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
