"""Non-LLM (gazetteer-based) canonicalization of well-known single/hyphenated-
word foreign city names in NER output.

Same bug class as geo_feature_gazetteer.py, but for cities instead of seas/
straits/gulfs: spaCy's Polish lemmatizer only reliably reduces a proper noun
to its nominative form when the name is well-represented in its training
data (e.g. "Chartumie"/"Chartumu" -> "Chartum"). A rare foreign city name
that the model doesn't know keeps its inflected surface as the "lemma"
too, e.g. "Omdurmanie" (locative: "w Omdurmanie") never resolves to
"Omdurman". ner_client.py's nominative-surface-preference heuristic
(NOMINATIVE_PREFERENCE_TYPES) doesn't help here either — it only applies to
multiword mentions (len(surface.split()) >= 2), and a single-word city name
mentioned only once, only in an inflected case, has no in-text nominative to
prefer anyway. The mangled inflected string then also breaks geocoding — the
geocoder is asked to resolve "Omdurmanie", which is not a place name (see
the doc #9394 investigation this module fixes: "Omdurmanie" verified=false,
while "Port Sudanu"/"Port Sudanem" leaked the genitive/instrumental case into
entity_text the same way).

This is a small, closed list of cities that recur in the geopolitics-focused
reporting Lenie ingests (currently: Sudan civil war coverage) — not an
exhaustive gazetteer (compare country_gazetteer.py's ~190-country list).
Matching mirrors geo_feature_gazetteer.py: word-stem regex against a
diacritic-stripped, lowercased mention, requiring the ENTIRE surface to
match — safe to call unconditionally on every geogName/placeName mention
without a prior "is this a known city" filter.
"""

import re
from dataclasses import dataclass
from functools import lru_cache

from unidecode import unidecode

# name_pl, variants: same token-pattern convention as geo_feature_gazetteer.py
# — a token ending in "*" matches as a word stem (\bTOKEN\w*), tokens
# separated by whitespace match adjacent words (optionally hyphenated, so
# "al faszir*" also matches the "Al-Faszir"/"Al-Fasziru" hyphenated surface).
_CITY_DATA: list[tuple[str, tuple[str, ...]]] = [
    # doc #9394: spaCy keeps the accusative "Gazę" as its lemma, so the
    # single-word nominative-preference path never gets a chance to recover
    # the canonical city name.
    ("Gaza", ("gaza", "gaze", "gazy", "gazie", "gazo")),
    ("Omdurman", ("omdurman*",)),
    ("Al-Faszir", ("al faszir*",)),
    # Two accepted transliterations of the same city — kept as separate
    # variants since the DSL only supports one trailing "*" per token.
    ("Al-Ubajjid", ("al ubajjid*", "al ubajid*")),
    ("Port Sudan", ("port sudan*",)),
]


@dataclass(frozen=True)
class CityPattern:
    regex: re.Pattern
    fixed_chars: int
    stem_tokens: int

    def fullmatch_with_suffix_limit(self, mention: str) -> bool:
        """Match a complete mention while allowing at most 4 chars per stem suffix."""
        if self.regex.fullmatch(mention) is None:
            return False
        mention_chars = len(re.sub(r"[\s-]+", "", mention))
        return mention_chars - self.fixed_chars <= 4 * self.stem_tokens


def _compile_variant(variant: str) -> CityPattern:
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
    return CityPattern(
        regex=re.compile(r"[\s-]+".join(parts)),
        fixed_chars=fixed_chars,
        stem_tokens=stem_tokens,
    )


@lru_cache(maxsize=1)
def _compiled_cities() -> tuple[tuple[str, tuple[CityPattern, ...]], ...]:
    return tuple((name_pl, tuple(_compile_variant(v) for v in variants)) for name_pl, variants in _CITY_DATA)


def canonical_city_name(mention: str) -> str | None:
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
        for name_pl, patterns in _compiled_cities()
        if any(pattern.fullmatch_with_suffix_limit(normalized) for pattern in patterns)
    }
    return next(iter(matches)) if len(matches) == 1 else None
