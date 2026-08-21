"""Non-LLM (gazetteer-based) canonicalization of well-known multi-word Polish
geographic feature names (seas, straits, gulfs, canals, oceans) in NER output.

spaCy's Span.lemma_ for a multiword geogName/placeName mention concatenates
per-token lemmas and loses Polish adjective-noun gender agreement (e.g. "Morze
Czerwone" -> lemma "Morze czerwony", see ner_client.py's
NOMINATIVE_PREFERENCE_TYPES comment). That module's nominative-surface
preference recovers the correct form only when at least one in-text mention is
actually in the nominative case; many documents mention a sea/strait/gulf only
in inflected cases ("Morza Czerwonego", "Zatoki Perskiej", "Morzu Czerwonym"),
leaving nothing to prefer and letting the mangled lemma (or an arbitrarily
chosen inflected surface) through to entity_text — and from there to the
geocoder, which can't resolve the inflected string either (see the "Darfurze"/
"Zatoki Perskiej" investigation this module fixes).

This is a small, closed list of well-known international features that
recur in geopolitics-focused reporting — not an exhaustive gazetteer (compare
country_gazetteer.py's ~190-country list). Matching mirrors that module:
word-stem regex against a diacritic-stripped, lowercased mention, requiring
the ENTIRE surface to match — safe to call unconditionally on every
geogName/placeName mention without a prior "is this a known feature" filter.
"""

import re
from dataclasses import dataclass
from functools import lru_cache

from unidecode import unidecode

# name_pl, variants: same token-pattern convention as country_gazetteer.py —
# a token ending in "*" matches as a word stem (\bTOKEN\w*), tokens separated
# by whitespace match adjacent words (optionally hyphenated).
_GEO_FEATURE_DATA: list[tuple[str, tuple[str, ...]]] = [
    ("Morze Czerwone", ("morz* czerwon*",)),
    ("Morze Czarne", ("morz* czarn*",)),
    ("Morze Śródziemne", ("morz* srodziemn*",)),
    ("Morze Bałtyckie", ("morz* baltyck*",)),
    ("Morze Północne", ("morz* polnocn*",)),
    ("Morze Kaspijskie", ("morz* kaspijsk*",)),
    ("Morze Arabskie", ("morz* arabski*",)),
    ("Morze Żółte", ("morz* zolt*",)),
    ("Morze Południowochińskie", ("morz* poludniowochinsk*",)),
    # "zatoka" has a palatalized dative/locative stem ("zatoce", k -> c) that
    # a plain "zatok*" prefix wildcard can't reach, hence the second variant.
    ("Zatoka Perska", ("zatok* persk*", "zatoc* persk*")),
    ("Zatoka Meksykańska", ("zatok* meksykansk*", "zatoc* meksykansk*")),
    ("Zatoka Gwinejska", ("zatok* gwinejsk*", "zatoc* gwinejsk*")),
    ("Zatoka Adeńska", ("zatok* adensk*", "zatoc* adensk*")),
    ("Zatoka Bengalska", ("zatok* bengalsk*", "zatoc* bengalsk*")),
    ("Zatoka Omańska", ("zatok* omansk*", "zatoc* omansk*")),
    ("Cieśnina Ormuz", ("ciesnin* ormuz*",)),
    ("Cieśnina Gibraltarska", ("ciesnin* gibraltarsk*",)),
    ("Cieśnina Bosfor", ("ciesnin* bosfor*",)),
    ("Kanał Sueski", ("kanal* suesk*",)),
    ("Kanał Panamski", ("kanal* panamsk*",)),
    ("Ocean Spokojny", ("ocean* spokojn*",)),
    ("Ocean Indyjski", ("ocean* indyjsk*",)),
    ("Ocean Atlantycki", ("ocean* atlantyck*",)),
    ("Ocean Arktyczny", ("ocean* arktyczn*",)),
]


@dataclass(frozen=True)
class GeoFeaturePattern:
    regex: re.Pattern
    fixed_chars: int
    stem_tokens: int

    def fullmatch_with_suffix_limit(self, mention: str) -> bool:
        """Match a complete mention while allowing at most 4 chars per stem suffix."""
        if self.regex.fullmatch(mention) is None:
            return False
        mention_chars = len(re.sub(r"[\s-]+", "", mention))
        return mention_chars - self.fixed_chars <= 4 * self.stem_tokens


def _compile_variant(variant: str) -> GeoFeaturePattern:
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
    return GeoFeaturePattern(
        regex=re.compile(r"[\s-]+".join(parts)),
        fixed_chars=fixed_chars,
        stem_tokens=stem_tokens,
    )


@lru_cache(maxsize=1)
def _compiled_features() -> tuple[tuple[str, tuple[GeoFeaturePattern, ...]], ...]:
    return tuple((name_pl, tuple(_compile_variant(v) for v in variants)) for name_pl, variants in _GEO_FEATURE_DATA)


def canonical_geo_feature_name(mention: str) -> str | None:
    """Return the canonical Polish name when one mention matches in full.

    Like country_gazetteer.canonical_country_name(), every gazetteer pattern
    must consume the complete normalized mention — safe for NER surface
    normalization without treating an arbitrary fragment as the entity.
    """
    normalized = unidecode(mention).strip().lower()
    if not normalized:
        return None
    matches = {
        name_pl
        for name_pl, patterns in _compiled_features()
        if any(pattern.fullmatch_with_suffix_limit(normalized) for pattern in patterns)
    }
    return next(iter(matches)) if len(matches) == 1 else None
