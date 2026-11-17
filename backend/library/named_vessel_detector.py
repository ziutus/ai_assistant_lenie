"""Detect vessel names following inflected Polish vessel indicators."""

import re

from library.named_event_detector import capitalized_word_ends

VESSEL_INDICATORS: dict[str, str] = {
    **dict.fromkeys(
        (
            "lotniskowiec",
            "lotniskowca",
            "lotniskowcowi",
            "lotniskowcu",
            "lotniskowcem",
            "lotniskowce",
            "lotniskowców",
            "lotniskowcom",
            "lotniskowcach",
            "lotniskowcami",
        ),
        "lotniskowiec",
    ),
    **dict.fromkeys(
        ("okręt", "okrętu", "okrętowi", "okręcie", "okrętem", "okręty", "okrętów", "okrętom", "okrętach", "okrętami"),
        "okręt",
    ),
    **dict.fromkeys(
        (
            "niszczyciel",
            "niszczyciela",
            "niszczycielowi",
            "niszczycielem",
            "niszczycielu",
            "niszczyciele",
            "niszczycieli",
            "niszczycielom",
            "niszczycielach",
            "niszczycielami",
        ),
        "niszczyciel",
    ),
    **dict.fromkeys(
        (
            "krążownik",
            "krążownika",
            "krążownikowi",
            "krążownikiem",
            "krążowniku",
            "krążowniki",
            "krążowników",
            "krążownikom",
            "krążownikach",
            "krążownikami",
        ),
        "krążownik",
    ),
    **dict.fromkeys(
        (
            "fregata",
            "fregaty",
            "fregacie",
            "fregatę",
            "fregatą",
            "fregato",
            "fregat",
            "fregatom",
            "fregatach",
            "fregatami",
        ),
        "fregata",
    ),
    **dict.fromkeys(
        (
            "korweta",
            "korwety",
            "korwecie",
            "korwetę",
            "korwetą",
            "korweto",
            "korwet",
            "korwetom",
            "korwetach",
            "korwetami",
        ),
        "korweta",
    ),
}
_INDICATOR = re.compile(r"\b(?:" + "|".join(VESSEL_INDICATORS) + r")\b", re.IGNORECASE)
_ADJECTIVE = re.compile(
    r"[ \u00a0]((?:podwodn|desantow|flagow|wojenn|bojow|atomow|pancern|rakietow|amerykańsk|rosyjsk|brytyjsk|chińsk)"
    r"[^\W\d_]*)(?![\w-])"
)


def detect_named_vessels(text: str) -> dict[str, dict]:
    """Group surface mentions by indicator lemma and case-folded vessel name."""
    vessels = {}
    names = {}
    for match in _INDICATOR.finditer(text):
        start = match.end()
        adjective = _ADJECTIVE.match(text, start)
        if adjective is not None and adjective.group(1).islower():
            start = adjective.end()
        ends = capitalized_word_ends(text, start, 3)
        if not ends:
            continue
        phrase = text[start + 1 : ends[-1]]
        if len(ends) == 1 and len(phrase) < 3:
            continue
        lemma = VESSEL_INDICATORS[match.group().casefold()]
        name = names.setdefault((lemma, phrase.casefold()), f"{lemma} {phrase}")
        vessel = vessels.setdefault(name, {"count": 0, "variants": [], "phrase": phrase})
        vessel["count"] += 1
        surface = text[match.start() : ends[-1]]
        if surface not in vessel["variants"]:
            vessel["variants"].append(surface)
    return vessels
