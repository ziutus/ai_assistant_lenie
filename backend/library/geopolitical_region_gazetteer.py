"""Non-LLM (gazetteer-based) canonicalization + synthetic geocoding for
well-known geopolitical/cultural macro-regions (Sahel, Bliski Wschod, Rog
Afryki...) that recur constantly in geopolitics-focused reporting but have no
single LocationIQ/OSM "place" object reliably behind them.

Unlike geo_feature_gazetteer.py/region_gazetteer.py/city_gazetteer.py (which
only fix NER lemmatization before handing the name to the live geocoder), a
name in this list is never sent to LocationIQ at all: live testing
2026-08-22 (doc #9394 "Sahel"/"Ormuz" investigation) showed a live query for
these names never returns anything useful, and the failure mode is
inconsistent enough that is_plausible_match() can't be trusted to reject it
every time:

- a real-but-wrong object that happens to share the exact name and passes the
  similarity check ("Kaukaz" -> a hamlet in Mazowieckie, Poland; "Bałkany" and
  "Maghreb" DO resolve correctly this way and are deliberately left off this
  list rather than duplicated here),
- a same-name unrelated business that also passes ("Bliski Wschod" -> a
  Warsaw restaurant; "Skandynawia" -> a chalet near Zator; "Europa Wschodnia"
  -> a hotel near Narva, Estonia),
- or a clean miss ("Rog Afryki", "Lewant").

Coordinates are an approximate representative point for map/tag display, not
an authoritative boundary - these are fuzzy cultural/political regions with
no single agreed-on border, unlike a country or an administrative
subdivision, so treat them as illustrative only.

Small, closed list - extend only for a region confirmed (by actually running
it through library.locationiq_client.geocode()/is_plausible_match()) to fail
or false-positive live, not speculatively.
"""

import re
from dataclasses import dataclass
from functools import lru_cache

from unidecode import unidecode

# name_pl, variants, lat, lon: same token-pattern convention as
# geo_feature_gazetteer.py/region_gazetteer.py - a token ending in "*"
# matches as a word stem (\bTOKEN\w*), tokens separated by whitespace match
# adjacent words (optionally hyphenated). A second variant is only needed
# when a Polish case ending palatalizes a letter inside the stem itself
# (e.g. Ameryka/Afryka's locative "-yce", k -> c - same issue as "zatoka" /
# "zatoce" in geo_feature_gazetteer.py).
_GEOPOLITICAL_REGION_DATA: list[tuple[str, tuple[str, ...], float, float]] = [
    ("Sahel", ("sahel*",), 15.0, 10.0),
    ("Bliski Wschód", ("blisk* wscho*",), 30.0, 45.0),
    ("Róg Afryki", ("rog* afryk*",), 8.0, 45.0),
    ("Europa Wschodnia", ("europ* wschodni*",), 50.0, 30.0),
    ("Europa Zachodnia", ("europ* zachodni*",), 48.0, 4.0),
    ("Afryka Subsaharyjska", ("afryk* subsaharyjsk*", "afryc* subsaharyjsk*"), 2.0, 20.0),
    ("Ameryka Łacińska", ("ameryk* lacinsk*", "ameryc* lacinsk*"), -10.0, -60.0),
    ("Azja Środkowa", ("azj* srodkow*",), 43.0, 65.0),
    ("Kaukaz", ("kaukaz*",), 42.0, 44.0),
    ("Lewant", ("lewant*", "lewanc*"), 34.0, 37.0),
    ("Azja Południowo-Wschodnia", ("azj* poludniowo* wschodni*",), 5.0, 105.0),
    ("Skandynawia", ("skandynawi*",), 62.0, 15.0),
]


@dataclass(frozen=True)
class GeopoliticalRegionPattern:
    regex: re.Pattern
    fixed_chars: int
    stem_tokens: int

    def fullmatch_with_suffix_limit(self, mention: str) -> bool:
        """Match a complete mention while allowing at most 4 chars per stem suffix."""
        if self.regex.fullmatch(mention) is None:
            return False
        mention_chars = len(re.sub(r"[\s-]+", "", mention))
        return mention_chars - self.fixed_chars <= 4 * self.stem_tokens


def _compile_variant(variant: str) -> GeopoliticalRegionPattern:
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
    return GeopoliticalRegionPattern(
        regex=re.compile(r"[\s-]+".join(parts)),
        fixed_chars=fixed_chars,
        stem_tokens=stem_tokens,
    )


@lru_cache(maxsize=1)
def _compiled_regions() -> tuple[tuple[str, tuple[GeopoliticalRegionPattern, ...], float, float], ...]:
    return tuple(
        (name_pl, tuple(_compile_variant(v) for v in variants), lat, lon)
        for name_pl, variants, lat, lon in _GEOPOLITICAL_REGION_DATA
    )


def canonical_geopolitical_region_name(mention: str) -> str | None:
    """Return the canonical Polish name when one mention matches in full.

    Like geo_feature_gazetteer.canonical_geo_feature_name(), every gazetteer
    pattern must consume the complete normalized mention - safe for NER
    surface normalization without treating an arbitrary fragment as the
    entity.
    """
    normalized = unidecode(mention).strip().lower()
    if not normalized:
        return None
    matches = {
        name_pl
        for name_pl, patterns, _lat, _lon in _compiled_regions()
        if any(pattern.fullmatch_with_suffix_limit(normalized) for pattern in patterns)
    }
    return next(iter(matches)) if len(matches) == 1 else None


def geopolitical_region_centroid(canonical_name: str) -> tuple[float, float] | None:
    """The approximate (lat, lon) for an already-canonicalized region name.

    Exact lookup only (unlike canonical_geopolitical_region_name(), which
    fuzzy-matches inflected NER surfaces) - callers pass the canonical
    spelling this module itself produced, the same convention as
    geocode_aliases.geocode_alias().
    """
    for name_pl, _patterns, lat, lon in _GEOPOLITICAL_REGION_DATA:
        if name_pl == canonical_name:
            return (lat, lon)
    return None
