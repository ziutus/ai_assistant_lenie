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
