"""Non-LLM (gazetteer-based) canonicalization of well-known multi-word foreign
administrative-region names (states, provinces) in NER output.

Same bug class as geo_feature_gazetteer.py/city_gazetteer.py, but for a third
category neither covers: a foreign administrative subdivision, not a physical
feature (sea/strait/gulf) or a city. spaCy's Span.lemma_ for a rare
adjective-noun region name mangles Polish gender agreement the same way it
does for "Morze Czerwone" (-> lemma "Morze czerwony") — and, being rare, is
never even mentioned in the nominative case in the source text, so
ner_client.py's NOMINATIVE_PREFERENCE_TYPES heuristic has nothing to prefer.
The inflected/mangled string then also breaks geocoding: LocationIQ resolves
"Kordofan Północny" cleanly (class=boundary, type=administrative, exact
match) but "Kordofanu Północnego" (genitive, doc #9394 — "stolicą Kordofanu
Północnego") returns an unrelated low-importance Warsaw waterworks station,
correctly rejected by is_plausible_match() but leaving the place unresolved.

Small, closed list — extend only for a specific region confirmed broken
against LocationIQ, not as a general transliteration table.
"""

import re
from dataclasses import dataclass
from functools import lru_cache

from unidecode import unidecode

# name_pl, variants: same token-pattern convention as geo_feature_gazetteer.py
# — a token ending in "*" matches as a word stem (\bTOKEN\w*), tokens
# separated by whitespace match adjacent words (optionally hyphenated).
_REGION_DATA: list[tuple[str, tuple[str, ...]]] = [
    ("Kordofan Północny", ("kordofan* polnocn*",)),
]


@dataclass(frozen=True)
class RegionPattern:
    regex: re.Pattern
    fixed_chars: int
    stem_tokens: int

    def fullmatch_with_suffix_limit(self, mention: str) -> bool:
        """Match a complete mention while allowing at most 4 chars per stem suffix."""
        if self.regex.fullmatch(mention) is None:
            return False
        mention_chars = len(re.sub(r"[\s-]+", "", mention))
        return mention_chars - self.fixed_chars <= 4 * self.stem_tokens


def _compile_variant(variant: str) -> RegionPattern:
    parts = []
    fixed_chars = 0
    stem_tokens = 0
    for token in variant.split():
        if token.endswith("*"):
            fixed = token[:-1]
            parts.append(r"\b" + re.escape(fixed) + r"\w*")
            fixed_chars += len(fixed)
            stem_tokens += 1
        else:
            parts.append(r"\b" + re.escape(token) + r"\b")
            fixed_chars += len(token)
    return RegionPattern(
        regex=re.compile(r"[\s-]+".join(parts)),
        fixed_chars=fixed_chars,
        stem_tokens=stem_tokens,
    )


@lru_cache(maxsize=1)
def _compiled_regions() -> tuple[tuple[str, tuple[RegionPattern, ...]], ...]:
    return tuple((name_pl, tuple(_compile_variant(v) for v in variants)) for name_pl, variants in _REGION_DATA)


def canonical_region_name(mention: str) -> str | None:
    """Return the canonical Polish name when one mention matches in full.

    Like geo_feature_gazetteer.canonical_geo_feature_name(), every gazetteer
    pattern must consume the complete normalized mention — safe for NER
    surface normalization without treating an arbitrary fragment as the
    entity.
    """
    normalized = unidecode(mention).strip().lower()
    if not normalized:
        return None
    matches = {
        name_pl
        for name_pl, patterns in _compiled_regions()
        if any(pattern.fullmatch_with_suffix_limit(normalized) for pattern in patterns)
    }
    return next(iter(matches)) if len(matches) == 1 else None
