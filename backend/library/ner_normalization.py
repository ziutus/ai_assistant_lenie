"""Deterministic Polish NER normalization rules loaded from versioned data."""

import json
import logging
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from library.country_gazetteer import canonical_country_name

logger = logging.getLogger(__name__)

RULES_PATH = Path(__file__).resolve().parents[1] / "data" / "ner_normalization.json"

# Bold/italic markdown markers (**, __) glue onto an adjacent entity when the
# source text has no whitespace before them (e.g. "Aktywów Państwowych.**-Tymczasem"),
# producing a spurious duplicate entity. Blanked out (not deleted) so character
# offsets used by _temporal_candidate_rows() stay stable.
_MARKDOWN_EMPHASIS_RE = re.compile(r"\*\*|__")

# [imgN]/[linkN] markers (article_cleaner.py's image/link substitution) glue
# onto an adjacent entity the same way markdown emphasis does (e.g.
# "Ministerstwo Obrony[link1]") — spaCy's tokenizer can then fold the marker
# (or part of it, up to but not including the closing bracket) into the
# entity span, producing surfaces like "Ministerstwo Obrony [link1". Blanked
# out for the same reason as markdown emphasis: same-length whitespace keeps
# character offsets stable.
_CONTENT_MARKER_RE = re.compile(r"\[(?:img|link)\d+\]")

# spaCy's Span.text reconstructs the *original* inter-token whitespace, so a
# multiword entity whose source markdown happened to line-wrap between two
# tokens (e.g. "Unia\nEuropejska") comes back with a literal newline/tab
# inside it. Left alone, that raw span becomes the display name/canonical_name
# stored in document_entities/organizations. Any run of whitespace inside a
# name is collapsed to one plain space — no entity's meaningful content is a
# newline or a tab, only the single space between words is.
_INTERNAL_WHITESPACE_RE = re.compile(r"\s+")

# Quotation marks that wrap quoted phrases in the source text and get glued
# onto an adjacent entity span (see strip_wrapping_quotes). ASCII '"' is in
# BOTH sets: Polish typing habitually mixes a Polish opener with an ASCII
# closer ("sudańskie Bractwo Muzułmańskie"), so '"' must pair with anything.
# Single-quote/apostrophe characters are excluded on purpose — they are
# legitimate name content (O'Brien, L'Oréal), not wrapping punctuation.
_OPENING_QUOTES = frozenset({'"', "\u201e", "\u201c", "\u00ab"})  # " „ “ «
_CLOSING_QUOTES = frozenset({'"', "\u201d", "\u00bb"})  # " ” »
_ALL_QUOTES = _OPENING_QUOTES | _CLOSING_QUOTES


def _has_pairing_quote(edge_quote: str, body: str) -> bool:
    """True when body still contains a quote that pairs with the edge one."""
    if edge_quote == '"':
        return any(char in _ALL_QUOTES for char in body)
    if edge_quote in _OPENING_QUOTES:
        return any(char in _CLOSING_QUOTES for char in body)
    return any(char in _OPENING_QUOTES for char in body)


def _strip_edge_quotes(text: str) -> str:
    """Repeatedly strip fully-wrapped or dangling quote chars at the edges."""
    result = text.strip()
    while len(result) >= 2:
        first, last = result[0], result[-1]
        if first in _ALL_QUOTES and last in _ALL_QUOTES:
            inner = result[1:-1].strip()
            if not inner:
                break
            result = inner
            continue
        if first in _ALL_QUOTES and not _has_pairing_quote(first, result[1:]):
            result = result[1:].strip()
            continue
        if last in _ALL_QUOTES and not _has_pairing_quote(last, result[:-1]):
            result = result[:-1].strip()
            continue
        break
    return result


def _unmatched_quote_positions(text: str) -> set[int]:
    """Indexes of quote characters with no pairing partner in text.

    Walks left to right: openers push, closers pop the pending opener. ASCII
    '"' is a wildcard — it closes whatever is pending when one exists,
    otherwise it opens. Whatever remains pending, plus closers seen with
    nothing pending, is unmatched.
    """
    pending: list[int] = []
    unmatched: set[int] = set()
    for index, char in enumerate(text):
        if char not in _ALL_QUOTES:
            continue
        if char == '"':  # wildcard: pair up if possible, else act as opener
            if pending:
                pending.pop()
            else:
                pending.append(index)
        elif char in _CLOSING_QUOTES:
            if pending:
                pending.pop()
            else:
                unmatched.add(index)
        else:
            pending.append(index)
    unmatched.update(pending)
    return unmatched


def strip_wrapping_quotes(text: str) -> str:
    """Strip quotation marks wrongly glued onto (or left dangling inside) an
    entity span.

    spaCy keeps a quotation mark inside the entity span when the source text
    wraps the phrase in quotes without intervening whitespace (live case:
    'jako "sudańskie Bractwo Muzułmańskie", zostali' produced the orgName span
    'Bractwo Muzułmańskie"' whose lemma then carried the stray '"' into
    organizations.canonical_name / organization_aliases). Three safe cases,
    applied repeatedly until nothing changes:
      * fully wrapped spans, including mixed quote kinds ('"Financial Times"',
        '\u201eprzyja\u017a\u0144\u201d'),
      * a dangling quote at one edge with no partner anywhere inside
        ('bractwo Muzu\u0142ma\u0144ski"', '"ZOO zaprasza\u0107'),
      * stacked edge quotes ('""Grot"').
    Additionally a quote left dangling *inside* the span (source text opened a
    quotation the span cuts short: 'Hans Pool "Bellingcat',
    'Donald Trump,"szejk') is removed, while a quote that legitimately closes
    an inner quotation keeps its partner and stays untouched ('Aleksander
    \u201eRocky\u201d', 'CBRE "European data Centres"'). Callers should run
    normalize_ner_text() afterwards to collapse any whitespace the removal
    leaves behind. Apostrophes/single quotes are out of scope entirely — they
    are legitimate name content (O'Brien, L'Oréal).
    """
    result = _strip_edge_quotes(text)
    unmatched = _unmatched_quote_positions(result)
    if unmatched:
        result = "".join(
            char for index, char in enumerate(result) if index not in unmatched
        ).strip()
        result = _strip_edge_quotes(result)
    return result


def strip_markdown_emphasis(text: str) -> str:
    """Blank out markdown bold/italic markers with same-length whitespace."""
    return _MARKDOWN_EMPHASIS_RE.sub(lambda m: " " * len(m.group(0)), text)


def strip_content_markers(text: str) -> str:
    """Blank out [imgN]/[linkN] markers with same-length whitespace."""
    return _CONTENT_MARKER_RE.sub(lambda m: " " * len(m.group(0)), text)


def normalize_ner_text(value: str) -> str:
    """Normalize storage/comparison text: NFC, collapse internal whitespace, strip ends."""
    return _INTERNAL_WHITESPACE_RE.sub(" ", unicodedata.normalize("NFC", value)).strip()


@lru_cache(maxsize=1)
def load_ner_normalization_rules() -> dict:
    """Load curated rules once per backend process."""
    try:
        with RULES_PATH.open(encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        logger.warning("NER normalization rules file does not exist: %s", RULES_PATH)
        return {}


def canonical_country_for_surface(surface: str) -> str | None:
    """Map one surface form to a canonical country, including curated aliases."""
    normalized = normalize_ner_text(surface)
    rules = load_ner_normalization_rules()

    abbreviations = rules.get("country_abbreviations", {})
    if normalized == normalized.upper() and normalized in abbreviations:
        return normalize_ner_text(abbreviations[normalized])

    demonyms = {
        normalize_ner_text(key).casefold(): normalize_ner_text(value)
        for key, value in rules.get("demonyms", {}).items()
    }
    demonym_country = demonyms.get(normalized.casefold())
    if demonym_country:
        return demonym_country
    return canonical_country_name(normalized)


def is_rejected_surface_lemma_pair(surface: str, lemma: str, pos: str | None) -> bool:
    """Check context-sensitive false-positive pairs; legacy payloads stay allowed."""
    if not pos:
        return False
    surface_key = normalize_ner_text(surface).casefold()
    lemma_key = normalize_ner_text(lemma).casefold()
    pos_key = pos.strip().upper()
    for rule in load_ner_normalization_rules().get("reject_surface_lemma_pairs", []):
        if normalize_ner_text(rule.get("surface", "")).casefold() != surface_key:
            continue
        if normalize_ner_text(rule.get("lemma", "")).casefold() != lemma_key:
            continue
        if pos_key in {value.upper() for value in rule.get("pos", [])}:
            return True
    return False
