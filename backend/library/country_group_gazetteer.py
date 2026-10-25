"""Named groups of states ("państwa bałtyckie") detected straight in a text.

A group is neither a place nor an organization: it stands for a closed list of countries, so
the review page shows it next to the chapter's countries with its members in a tooltip. spaCy
reports such a phrase as a place or not at all, so the text itself is scanned for a closed list
of phrases, the same text-grounded idea (and pattern DSL) as place_mention_gazetteer.py.
Groups are derived on read and never stored: nothing to keep in step when the list grows.
"""

import re
from collections import Counter

from unidecode import unidecode

from library.city_gazetteer import CityPattern, compile_variant

# name_pl -> (member country names as in country_gazetteer, stem patterns of the phrases).
_GROUP_DATA: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = [
    ("Państwa bałtyckie", ("Litwa", "Łotwa", "Estonia"),
     ("panstw* baltyck*", "kraj* baltyck*", "panstw* nadbaltyck*", "kraj* nadbaltyck*")),
    ("Kraje nordyckie", ("Dania", "Finlandia", "Islandia", "Norwegia", "Szwecja"),
     ("kraj* nordyck*", "panstw* nordyck*")),
    ("Beneluks", ("Belgia", "Holandia", "Luksemburg"), ("beneluks*",)),
    ("Grupa Wyszehradzka", ("Czechy", "Polska", "Słowacja", "Węgry"),
     ("grup* wyszehradzk*", "kraj* wyszehradzk*", "panstw* wyszehradzk*")),
    ("Państwa Zatoki Perskiej", ("Arabia Saudyjska", "Bahrajn", "Katar", "Kuwejt", "Oman", "Zjednoczone Emiraty Arabskie"),
     ("panstw* zatoki perskiej", "kraj* zatoki perskiej", "panstw* zatoki", "kraj* zatoki")),
    ("Kaukaz Południowy", ("Armenia", "Azerbejdżan", "Gruzja"),
     ("panstw* kaukazu poludniowego", "kraj* kaukazu poludniowego", "poludniow* kaukaz*")),
    ("Azja Środkowa", ("Kazachstan", "Kirgistan", "Tadżykistan", "Turkmenistan", "Uzbekistan"),
     ("panstw* azji srodkowej", "kraj* azji srodkowej")),
]

_COMPILED: tuple[tuple[str, tuple[str, ...], tuple[CityPattern, ...]], ...] = tuple(
    (name_pl, members, tuple(compile_variant(variant) for variant in variants))
    for name_pl, members, variants in _GROUP_DATA
)


def _fold(text: str) -> str:
    """Lowercase ASCII copy with exactly one character per original character."""
    return "".join((unidecode(char) or char)[:1] for char in text.lower())


def group_members(name_pl: str) -> tuple[str, ...]:
    return next((members for name, members, _patterns in _COMPILED if name == name_pl), ())


def detect_country_groups(text: str) -> list[dict]:
    """[{name, members, variants (surface forms found), count}] for the groups mentioned in ``text``."""
    if not text:
        return []
    folded = _fold(text)
    result = []
    for name_pl, members, patterns in _COMPILED:
        surfaces: Counter = Counter()
        seen_spans: set[tuple[int, int]] = set()
        for pattern in patterns:
            for match in pattern.regex.finditer(folded):
                span = match.span()
                # Patterns are listed longest first: a shorter one overlapping a counted span is the same mention.
                if any(span[0] < end and start < span[1] for start, end in seen_spans) \
                        or not pattern.fullmatch_with_suffix_limit(match.group()):
                    continue
                seen_spans.add(span)
                surfaces[re.sub(r"\s+", " ", text[span[0]:span[1]]).strip()] += 1
        if surfaces:
            result.append({
                "name": name_pl, "members": list(members),
                "variants": list(surfaces), "count": sum(surfaces.values()),
            })
    return result
