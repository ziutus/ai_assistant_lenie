"""Whole-form place names whose geocoder proposals require human approval."""

from dataclasses import dataclass
from collections.abc import Iterable

from unidecode import unidecode

# Geographic head nouns -> inflected forms (folded: no diacritics, lowercase). A bare head ("Zatoka") names a
# KIND of feature, not a place; the geocoder would pick any bay in the world. Extend only with a noun that names
# a kind of feature, never one that is itself a name. `library/generic_geo_heads.py` folds a bare head into the
# one named feature of the document ("Zatoka Perska") when the text supports it.
HEAD_FORMS: dict[str, tuple[str, ...]] = {
    "zatoka": ("zatoka", "zatoki", "zatoce", "zatoke", "zatok"),
    "morze": ("morze", "morza", "morzu", "morzem"),
    "ocean": ("ocean", "oceanu", "oceanie", "oceanem"),
    "ciesnina": ("ciesnina", "ciesniny", "ciesninie", "ciesnine"),
    "polwysep": ("polwysep", "polwyspu", "polwyspie", "polwyspem"),
    "jezioro": ("jezioro", "jeziora", "jezioru", "jeziorze", "jeziorem"),
    "pustynia": ("pustynia", "pustyni", "pustynie"),
    "kanal": ("kanal", "kanalu", "kanale", "kanalem"),
}
ALL_HEAD_FORMS = frozenset(form for forms in HEAD_FORMS.values() for form in forms)


@dataclass(frozen=True)
class Rule:
    id: str
    reason: str
    forms: frozenset[str]
    # Match only the entity's own name (and the geocoder's canonical name), not its surface variants: a
    # named feature ("Zatoka Perska") may carry the bare head ("Zatoce") as a variant without being generic.
    name_only: bool = False


RULES = (
    Rule("generic_huty", "Nazwa może oznaczać zakład przemysłowy.", frozenset({"huty", "huti", "huta"})),
    Rule("generic_poludnie", "Nazwa może oznaczać kierunek geograficzny lub porę dnia.", frozenset({"poludnie"})),
    Rule(
        "generic_geo_head",
        "Nazwa oznacza rodzaj obiektu geograficznego (zatoka, morze…), nie konkretne miejsce.",
        ALL_HEAD_FORMS,
        name_only=True,
    ),
)


def match_generic_place_name(
    name: str, variants: Iterable[str] | None, canonical_name: str | None = None,
) -> Rule | None:
    own_forms = {unidecode(value).strip().casefold() for value in (name, canonical_name) if value}
    forms = own_forms | {unidecode(value).strip().casefold() for value in (variants or []) if value}
    return next((rule for rule in RULES if rule.forms & (own_forms if rule.name_only else forms)), None)
