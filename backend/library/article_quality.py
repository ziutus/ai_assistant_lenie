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

# Sygnaly stockowe/agencyjne w dowolnym miejscu krótkiej linii
_CAPTION_AGENCY_RE = re.compile(
    r"(?:zdj[eę]cie\s+ilustracyjne|shutterstock|getty\s*images?|east\s+news|"
    r"adobe\s+stock|istock(?:photo)?|depositphotos|123rf|unsplash|pexels|"
    r"\bPAP\s*/|/\s*PAP\b|\bEPA\b|\bAFP\b|\bReuters\b|\bForum\b\s*/|/\s*Forum\b)",
    re.IGNORECASE,
)

# Podpis bywa dłuższy niż _CAPTION_MAX_CHARS, ale linia KOŃCZĄCA SIĘ
# "(zdjęcie ilustracyjne)" to zawsze podpis, niezależnie od długości.
_CAPTION_SUFFIX_RE = re.compile(r"\(zdj[eę]cie\s+ilustracyjne\)\s*$", re.IGNORECASE)

_CLICKBAIT_RE = re.compile(
    r"(?:nie uwierzysz|szok(?:uj[aą]c\w*)?\b|musisz to zobaczy[ćc]|zobacz,? co|"
    r"a[żz] trudno uwierzy[ćc]|to zmieni (?:tw[oó]j|wszystko)|jednym trikiem|"
    r"zdradzi[łl]a? sekret|internauci oszaleli|wszyscy o (?:tym|niej|nim) m[oó]wi[aą])",
    re.IGNORECASE,
)


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


def is_clickbait_title(title: str | None) -> bool:
    return bool(title and _CLICKBAIT_RE.search(title))


def _llm_rubric(text: str, model: str) -> dict | None:
    """Jedno wywołanie LLM: oceny 0-5 w trzech wymiarach staranności.

    Zwraca {"zrodla": n, "glebia": n, "jezyk": n, "uzasadnienie": "..."}
    albo None, gdy wywołanie/parsowanie się nie powiedzie.
    """
    from library.chunk_llm_analysis import call_model

    prompt = f"""Oceń staranność poniższego artykułu w trzech wymiarach, każdy w skali 0-5:
- "zrodla": czy autor powołuje się na konkretne źródła (dokumenty, dane, ekspertów z nazwiska), czy tylko ogólniki typu "media donoszą",
- "glebia": czy tekst zawiera własną analizę i kontekst, czy jest przepisaną notką/depeszą,
- "jezyk": poprawność i staranność językowa.

Zwróć TYLKO obiekt JSON bez dodatkowego tekstu:
{{"zrodla": 0, "glebia": 0, "jezyk": 0, "uzasadnienie": "1-2 zdania"}}

--- ARTYKUŁ ---
{text[:RUBRIC_INPUT_CHARS]}
--- KONIEC ---"""
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
    noise_len = sum(
        len(s.get("original") or "") for s in chunk_sections if s.get("type") != "TEMAT"
    )
    total_len = len(temat_text) + noise_len

    full_text = "\n".join((s.get("original") or "") for s in chunk_sections)
    captions = count_photo_captions(full_text)
    noise_share = (noise_len / total_len) if total_len else 0.0

    penalties: dict[str, int] = {}
    if captions:
        penalties["photo_captions"] = min(15, 5 * captions)
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
        rubric = _llm_rubric(temat_text, model)
        if rubric:
            rubric_sum = rubric["zrodla"] + rubric["glebia"] + rubric["jezyk"]
            penalties["llm_rubric"] = (15 - rubric_sum) * 2  # 0-30

    score = max(0, 100 - sum(penalties.values()))
    return {
        "score": score,
        "penalties": penalties,
        "signals": {
            "photo_captions": captions,
            "noise_share": round(noise_share, 3),
            "temat_chars": len(temat_text),
        },
        "llm_rubric": rubric,
        "model": model if rubric else None,
        "computed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
