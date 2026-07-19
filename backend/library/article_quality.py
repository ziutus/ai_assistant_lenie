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
from urllib.parse import urlparse

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
    r"(?:\bPAP\s*/|/\s*PAP\b|\bEPA\b|\bAFP\b|\bReuters\b|\bBloomberg\b|"
    r"\bForum\b\s*/|/\s*Forum\b|agencj\w+\s+wyborcz\w+)",
    re.IGNORECASE,
)

_CAPTION_AGENCY_RE = re.compile(
    r"(?:zdj[eę]cie\s+ilustracyjne|shutterstock|getty\s*images?|east\s+news|"
    r"adobe\s+stock|istock(?:photo)?|depositphotos|123rf|unsplash|pexels|"
    r"domena\s+publiczna|\bcc\s+by(?:-sa)?\b|creative\s+commons|archiwum\s+prywatne|©|"
    r"\bPAP\s*/|/\s*PAP\b|\bEPA\b|\bAFP\b|\bReuters\b|\bBloomberg\b|"
    r"\bForum\b\s*/|/\s*Forum\b|agencj\w+\s+wyborcz\w+)",
    re.IGNORECASE,
)

# Ekstrakcja Interii skleja podpis, fotografa i agencję bez separatora
# ("...dronowychBloombergBloomberg", "...wojskaTHOMAS SAMSONAFP"), przez co
# \b we wzorcach agencji nie znajduje granicy słowa. Rozklejenie: spacja na
# granicy mała→wielka litera oraz przed akronimem agencji doklejonym do
# wersalikowego nazwiska (min. 3 wielkie litery przed akronimem, żeby nie
# rozcinać zwykłych słów w stylu "RZEPA").
_GLUED_LOWER_UPPER_RE = re.compile(r"(?<=[a-ząćęłńóśźż])(?=[A-ZĄĆĘŁŃÓŚŹŻ])")
_GLUED_ACRONYM_RE = re.compile(r"(?<=[A-ZĄĆĘŁŃÓŚŹŻ]{3})(?=(?:AFP|EPA|PAP)\s*$)")


def _deglue_credits(line: str) -> str:
    """Kopia linii z przywróconymi granicami słów w sklejonym credicie."""
    return _GLUED_ACRONYM_RE.sub(" ", _GLUED_LOWER_UPPER_RE.sub(" ", line))

# Zdjęcie z agencji fotograficznej należącej do wydawcy artykułu to materiał
# własny redakcji (waga 0), nie zewnętrzna agencja — mapa: wzorzec nazwy
# agencji w podpisie -> domeny serwisów tego wydawcy.
PUBLISHER_OWN_AGENCIES: list[tuple[re.Pattern, tuple[str, ...]]] = [
    # Agencja Wyborcza.pl — agencja fotograficzna Agory
    (re.compile(r"agencj\w+\s+wyborcz\w+", re.IGNORECASE),
     ("wyborcza.pl", "gazeta.pl", "wyborcza.biz", "wysokieobcasy.pl", "tokfm.pl")),
]


def _is_publisher_own_agency(line: str, url: str | None) -> bool:
    """Czy podpis wskazuje agencję fotograficzną wydawcy serwisu z `url`?"""
    if not url:
        return False
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    if not host:
        return False
    for agency_re, domains in PUBLISHER_OWN_AGENCIES:
        if agency_re.search(line) and any(
            host == domain or host.endswith("." + domain) for domain in domains
        ):
            return True
    return False

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

# Nagłówek bywa pogrubiony markdownem ("**Źródła:**"), stąd tolerancja [*_].
_REFERENCES_HEADING_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?[*_]{0,3}\s*(?:źródła|zrodla|bibliografia|references|literatura)"
    r"\s*:?\s*[*_]{0,3}\s*$",
    re.IGNORECASE,
)

# Pozycja listy pod nagłówkiem źródeł: "* The Guardian — \"tytuł\"", "- MSZ",
# "1. Raport GUS". Wymagany marker listy — luźny akapit pod nagłówkiem to
# już zwykła treść, nie pozycja bibliografii.
_BIBLIOGRAPHY_ITEM_RE = re.compile(r"^(?:[*\-•]|\d{1,2}[.)])\s+(\S.*)$")

# Separator "wydawca — tytuł" wewnątrz pozycji bibliografii.
_BIBLIOGRAPHY_NAME_SPLIT_RE = re.compile(r"\s+[—–]\s+|\s+-\s+")


def extract_press_bibliography(text: str) -> list[dict]:
    """Pozycje listy źródeł prasowych/instytucjonalnych pod nagłówkiem "Źródła:".

    Deterministyczny sygnał staranności dla bibliografii bez URL-i i DOI
    (identyfikatory naukowe obsługuje cited_publications) — np.
    "* The Guardian — \"tytuł\"" albo "* MSZ". Lista kończy się na pierwszej
    linii bez markera wypunktowania.

    Zwraca [{"source_name": "The Guardian", "raw_entry": "..."}, ...].
    """
    entries: list[dict] = []
    in_section = False
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if _REFERENCES_HEADING_RE.match(stripped):
            in_section = True
            continue
        if not in_section:
            continue
        match = _BIBLIOGRAPHY_ITEM_RE.match(stripped)
        if not match:
            in_section = False
            continue
        raw_entry = match.group(1).strip()
        name = _BIBLIOGRAPHY_NAME_SPLIT_RE.split(raw_entry, maxsplit=1)[0]
        name = name.strip().strip("*_\"„”").strip()
        if name:
            entries.append({"source_name": name, "raw_entry": raw_entry})
    return entries


def is_references_section(text: str) -> bool:
    """True for a non-content chunk consisting of a references list.

    Such chunks are intentionally excluded from embeddings, but they are
    evidence of diligence and must not count as editorial noise. A references
    list is recognised either by scholarly identifiers (PMID/DOI) or by a
    bulleted press bibliography under the heading.
    """
    from library.cited_publications import extract_cited_publications

    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    if not lines or not _REFERENCES_HEADING_RE.match(lines[0]):
        return False
    return bool(extract_cited_publications(text) or extract_press_bibliography(text))


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
    if _CAPTION_PREFIX_RE.match(bare) or _CAPTION_AGENCY_RE.search(bare):
        return True
    deglued = _deglue_credits(bare)
    return deglued != bare and bool(_CAPTION_AGENCY_RE.search(deglued))


def count_photo_captions(text: str) -> int:
    """Liczba linii-podpisów zdjęć w tekście (sygnał do oceny staranności)."""
    if not text:
        return 0
    return sum(1 for line in text.splitlines() if is_photo_caption_line(line))


def photo_caption_candidates(text: str, url: str | None = None) -> list[dict]:
    """Wykryte podpisy wraz z kategorią — dowody dla quality i podpowiedzi UI.

    url: adres dokumentu; pozwala rozpoznać agencję własną wydawcy
    (PUBLISHER_OWN_AGENCIES) i nadać jej kategorię materiału własnego."""
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
        deglued = _deglue_credits(stripped)
        lowered = deglued.lower()
        if "domena publiczna" in lowered:
            category = "public_domain"
        elif re.search(r'\bcc\s+by(?:-sa)?\b|creative commons', lowered):
            category = "creative_commons"
        elif "archiwum prywatne" in lowered:
            category = "own_or_private_archive"
        elif re.search(r'zdj[eę]cie\s+ilustracyjne', lowered):
            category = "illustrative"
        elif _CAPTION_STOCK_RE.search(deglued):
            category = "stock"
        elif _is_publisher_own_agency(deglued, url):
            category = "own_or_private_archive"
        elif _CAPTION_AGENCY_SOURCE_RE.search(deglued):
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


def _llm_rubric(
    text: str,
    model: str,
    cited_publications: list[dict] | None = None,
    press_bibliography: list[dict] | None = None,
) -> dict | None:
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
    # Bibliografia prasowa (sekcja "Źródła:") bywa wydzielona do osobnego
    # chunka ZRODLA — rubryka widzi tylko TEMAT, więc listę trzeba dołożyć.
    for item in press_bibliography or []:
        citation_lines.append(f"- {item['source_name']}: {item['raw_entry']}")
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
    press_bibliography = extract_press_bibliography(full_text)
    caption_evidence = photo_caption_candidates(full_text, getattr(doc, "url", None))
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
    if not (getattr(doc, "byline", None) or "").strip():
        penalties["missing_author"] = 10
    if noise_share > 0:
        penalties["noise_share"] = min(20, round(noise_share * 50))
    if len(temat_text.strip()) < SHORT_TEXT_CHARS:
        penalties["short_text"] = 10
    if is_clickbait_title(getattr(doc, "title", None)):
        penalties["clickbait_title"] = 5

    rubric = None
    if model and temat_text.strip():
        rubric = _llm_rubric(temat_text, model, cited_publications, press_bibliography)
        if rubric:
            # Structured identifiers and a named press bibliography are
            # grounded evidence, not an LLM guess. Prevent a separated
            # references chunk from being scored as "no sources" merely
            # because the rubric sees TEMAT prose separately.
            named_sources = len(cited_publications) + len(press_bibliography)
            citation_floor = 4 if named_sources >= 3 else 3 if named_sources == 2 else 2 if named_sources else 0
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
            "press_bibliography": len(press_bibliography),
            "press_bibliography_sources": [
                item["source_name"] for item in press_bibliography[:20]
            ],
        },
        "llm_rubric": rubric,
        "model": model if rubric else None,
        "computed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
