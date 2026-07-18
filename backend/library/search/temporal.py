"""Deterministic historical-period relations and anchors (stage 5 of the plan).

The LLM is good at recognizing which historical anchor a phrase like
"koniec II wojny światowej" refers to; arithmetic on it ("what year bound
does that imply") is better done deterministically and auditably here than
trusted blindly from the model's own computation. This module only ever
produces subject_period_start_year/subject_period_end_year bounds — it
never touches published_on_*/ingested_at_* — so a historical period can
never accidentally become a publication or ingestion date (the stage 5
acceptance criterion).

Bump ANCHOR_DICTIONARY_VERSION whenever HISTORICAL_ANCHORS changes; a wrong
entry silently mis-dates every future query that mentions it.
"""

from __future__ import annotations

from enum import Enum

from unidecode import unidecode

from library.search.types import MAX_SUBJECT_YEAR, MIN_SUBJECT_YEAR, normalize_year_range

ANCHOR_DICTIONARY_VERSION = "1"
DEFAULT_AROUND_SPAN_YEARS = 5


class TemporalRelation(str, Enum):
    EXACT = "exact"
    BEFORE = "before"
    AFTER = "after"
    BETWEEN = "between"
    AROUND = "around"


class TemporalRelationError(ValueError):
    """Raised when a relation is given inputs it cannot resolve from."""


# Anchor phrase (normalized via _normalize_anchor) -> the single year it
# denotes. The relation (before/after/around/exact) supplies the direction;
# a "between" query needs two anchors and is not resolved from this
# dictionary alone.
HISTORICAL_ANCHORS: dict[str, int] = {
    "koniec ii wojny swiatowej": 1945,
    "koniec drugiej wojny swiatowej": 1945,
    "poczatek ii wojny swiatowej": 1939,
    "poczatek drugiej wojny swiatowej": 1939,
    "wybuch ii wojny swiatowej": 1939,
    "wybuch drugiej wojny swiatowej": 1939,
    "koniec i wojny swiatowej": 1918,
    "koniec pierwszej wojny swiatowej": 1918,
    "poczatek i wojny swiatowej": 1914,
    "poczatek pierwszej wojny swiatowej": 1914,
    "wybuch i wojny swiatowej": 1914,
    "wybuch pierwszej wojny swiatowej": 1914,
    "upadek muru berlinskiego": 1989,
    "obalenie muru berlinskiego": 1989,
    "rozpad zsrr": 1991,
    "rozpad zwiazku radzieckiego": 1991,
    "koniec zimnej wojny": 1991,
    "poczatek zimnej wojny": 1947,
    "transformacja ustrojowa": 1989,
    "wejscie polski do unii europejskiej": 2004,
    "wstapienie polski do unii europejskiej": 2004,
    "wejscie polski do ue": 2004,
    "wstapienie polski do ue": 2004,
    "wejscie polski do nato": 1999,
    "wstapienie polski do nato": 1999,
    "zamachy z 11 wrzesnia": 2001,
    "atak na world trade center": 2001,
}


def _normalize_anchor(text: str) -> str:
    return " ".join(unidecode(text).casefold().split())


def resolve_anchor(anchor_text: str | None) -> int | None:
    """Look up a known historical anchor phrase; None when not recognized.

    A miss is not an error — an unrecognized anchor simply cannot be
    resolved to a year and the caller keeps the field unfilled rather than
    guessing.
    """
    if not anchor_text or not anchor_text.strip():
        return None
    return HISTORICAL_ANCHORS.get(_normalize_anchor(anchor_text))


def resolve_relation(
    relation: TemporalRelation | str,
    *,
    year: int | None = None,
    year_end: int | None = None,
    span_years: int = DEFAULT_AROUND_SPAN_YEARS,
) -> tuple[int | None, int | None, str | None]:
    """Turn one relation + reference year(s) into a (start, end, warning) bound.

    Bounds are inclusive on the given side; the open side is None (matches
    ParsedSearchQuery's own "no bound" convention). BEFORE/AFTER include the
    reference year itself — a document "before 1945" may well still discuss
    1945. AROUND is always approximate and always carries a Polish warning
    (plan rule: mark approximations).
    """
    relation = TemporalRelation(relation)

    if relation is TemporalRelation.EXACT:
        if year is None:
            raise TemporalRelationError("exact relation requires year")
        return year, year, None

    if relation is TemporalRelation.BEFORE:
        if year is None:
            raise TemporalRelationError("before relation requires year")
        return None, year, None

    if relation is TemporalRelation.AFTER:
        if year is None:
            raise TemporalRelationError("after relation requires year")
        return year, None, None

    if relation is TemporalRelation.BETWEEN:
        if year is None or year_end is None:
            raise TemporalRelationError("between relation requires year and year_end")
        start, end, _swap_warning = normalize_year_range(year, year_end)
        return start, end, None

    # AROUND
    if year is None:
        raise TemporalRelationError("around relation requires year")
    start = max(MIN_SUBJECT_YEAR, year - span_years)
    end = min(MAX_SUBJECT_YEAR, year + span_years)
    return start, end, f"Przybliżony okres: około roku {year} (+/- {span_years} lat)."


def enrich_subject_period(
    *,
    start_year: int | None,
    end_year: int | None,
    relation: str | None,
    anchor_text: str | None,
) -> tuple[int | None, int | None, str | None]:
    """Fill missing subject_period bounds from a relation + anchor, if possible.

    Called only when the LLM already left both bounds null — an explicit
    numeric year from the LLM always wins and is never overridden here, so
    this is purely a fallback for anchors the model recognized but could
    not (or chose not to) compute a year for itself. Returns the possibly
    unchanged (start_year, end_year) plus an optional diagnostic warning;
    never raises and never touches any field but the two subject_period
    bounds it returns.
    """
    if start_year is not None or end_year is not None:
        return start_year, end_year, None
    if not relation:
        return start_year, end_year, None

    try:
        parsed_relation = TemporalRelation(relation)
    except ValueError:
        return start_year, end_year, None

    if parsed_relation is TemporalRelation.BETWEEN:
        # A "between" bound needs two explicit years; a single anchor
        # phrase cannot supply both, so there is nothing to resolve here.
        return start_year, end_year, None

    anchor_year = resolve_anchor(anchor_text)
    if anchor_year is None:
        if anchor_text:
            return start_year, end_year, f"Nie rozpoznano kotwicy czasowej: {anchor_text!r}."
        return start_year, end_year, None

    resolved_start, resolved_end, warning = resolve_relation(parsed_relation, year=anchor_year)
    if warning is None:
        warning = f"Rok ustalony na podstawie znanego wydarzenia: {anchor_text} = {anchor_year}."
    return resolved_start, resolved_end, warning


__all__ = [
    "ANCHOR_DICTIONARY_VERSION",
    "DEFAULT_AROUND_SPAN_YEARS",
    "HISTORICAL_ANCHORS",
    "TemporalRelation",
    "TemporalRelationError",
    "enrich_subject_period",
    "resolve_anchor",
    "resolve_relation",
]
