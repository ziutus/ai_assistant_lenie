"""Text-grounded detection of place names that spaCy misses (a NER supplement).

The other gazetteers (city_gazetteer.py, geo_feature_gazetteer.py, ...) only canonicalize a
mention spaCy already found. Some real places never reach them: doc #10872 says "Kaliningradu,
czyli królewca" (lowercase, so aggregate_entities_detailed() drops it), "obwód kaliningradzki"
(spaCy tags only the adjective, POS=ADJ, which is filtered out) and "przesmyk suwalski" (the same).
This module scans the text itself for a closed list of such names and returns them as mentions,
the same deterministic-supplement idea as information_provenance.extract_known_reporting_sources().

The pattern DSL is city_gazetteer's: a token ending in "*" is a word stem, tokens are adjacent words.
Matching runs on a diacritic-stripped, lowercased copy of the text (length-preserving, so a match
maps straight back to the original surface form). The seed lives in code; rows of kind
``place_mention`` in ner_gazetteer_entries (ADR-029) extend it without a deploy.
"""

import logging
import re
import threading
from collections import Counter

from unidecode import unidecode

from library import ner_gazetteer_store
from library.city_gazetteer import CityPattern, compile_variant

logger = logging.getLogger(__name__)

# name_pl is the canonical display name of the entity the mentions are counted under: a surface
# form of an existing place ("królewca" -> Kaliningrad) or a place of its own.
_PLACE_MENTION_DATA: list[tuple[str, tuple[str, ...]]] = [
    # doc #10872: "czyli królewca" (lowercase) is the Polish name of the same city.
    ("Kaliningrad", ("krolewiec", "krolewc*")),
    # doc #10872: spaCy tags only the adjective "kaliningradzki" (POS=ADJ, dropped).
    ("Obwód Kaliningradzki", ("obwod* kaliningradzk*", "obwodz* kaliningradzk*")),
    # doc #10872: "przez przesmyk suwalski" — spaCy tags only "suwalski" (POS=ADJ, dropped).
    ("Przesmyk Suwalski", ("przesmyk* suwalsk*",)),
]

_compiled_state: tuple[int, tuple[tuple[str, tuple[CityPattern, ...]], ...]] | None = None
_compiled_lock = threading.Lock()


def _compiled_mentions() -> tuple[tuple[str, tuple[CityPattern, ...]], ...]:
    """Seed plus database entries, recompiled when the gazetteer store refreshes."""
    global _compiled_state
    version = ner_gazetteer_store.cache_version()
    state = _compiled_state
    if state is not None and state[0] == version:
        return state[1]
    with _compiled_lock:
        merged: dict[str, list[str]] = {name_pl: list(variants) for name_pl, variants in _PLACE_MENTION_DATA}
        by_folded = {name_pl.casefold(): name_pl for name_pl in merged}
        for entry in ner_gazetteer_store.get_entries(ner_gazetteer_store.KIND_PLACE_MENTION):
            name_pl = by_folded.setdefault(entry.name_pl.casefold(), entry.name_pl)
            merged.setdefault(name_pl, []).extend(entry.patterns)
        compiled = []
        for name_pl, variants in merged.items():
            patterns = []
            for variant in variants:
                try:
                    patterns.append(compile_variant(variant))
                except re.error:
                    logger.warning("Invalid place mention pattern %r for %r skipped", variant, name_pl)
            compiled.append((name_pl, tuple(patterns)))
        _compiled_state = (version, tuple(compiled))
        return _compiled_state[1]


def _fold(text: str) -> str:
    """Lowercase ASCII copy with exactly one character per original character."""
    return "".join((unidecode(char) or char)[:1] for char in text.lower())


def detect_place_mentions(text: str, raw_entities: list[dict] | None = None) -> dict[str, Counter]:
    """{canonical name: Counter(surface form -> mentions spaCy did not already report)}.

    A surface form spaCy already reported (same text, any label) is not counted again, so a
    capitalized "Królewiec" found by both stays one mention.
    """
    if not text:
        return {}
    folded = _fold(text)
    already: Counter = Counter(
        (entity.get("text") or "").casefold() for entity in (raw_entities or [])
    )
    found: dict[str, Counter] = {}
    for name_pl, patterns in _compiled_mentions():
        seen_spans: set[tuple[int, int]] = set()
        for pattern in patterns:
            for match in pattern.regex.finditer(folded):
                span = match.span()
                # Two patterns of one name can cover the same words ("obwod*" and "obwodz*").
                if span in seen_spans or not pattern.fullmatch_with_suffix_limit(match.group()):
                    continue
                seen_spans.add(span)
                surface = " ".join(text[span[0]:span[1]].split())
                found.setdefault(name_pl, Counter())[surface] += 1
    result: dict[str, Counter] = {}
    for name_pl, surfaces in found.items():
        remaining = Counter()
        for surface, count in surfaces.items():
            skipped = min(count, already[surface.casefold()])
            already[surface.casefold()] -= skipped
            if count - skipped > 0:
                remaining[surface] = count - skipped
        if remaining:
            result[name_pl] = remaining
    return result
