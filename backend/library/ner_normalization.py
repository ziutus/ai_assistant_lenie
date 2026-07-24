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


def strip_markdown_emphasis(text: str) -> str:
    """Blank out markdown bold/italic markers with same-length whitespace."""
    return _MARKDOWN_EMPHASIS_RE.sub(lambda m: " " * len(m.group(0)), text)


def normalize_ner_text(value: str) -> str:
    """Normalize storage/comparison text without changing meaningful spacing."""
    return unicodedata.normalize("NFC", value).strip()


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
