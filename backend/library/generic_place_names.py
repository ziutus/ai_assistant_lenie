"""Whole-form place names whose geocoder proposals require human approval."""

from dataclasses import dataclass
from collections.abc import Iterable

from unidecode import unidecode


@dataclass(frozen=True)
class Rule:
    id: str
    reason: str
    forms: frozenset[str]


RULES = (
    Rule("generic_huty", "Nazwa może oznaczać zakład przemysłowy.", frozenset({"huty", "huti", "huta"})),
    Rule("generic_poludnie", "Nazwa może oznaczać kierunek geograficzny lub porę dnia.", frozenset({"poludnie"})),
)


def match_generic_place_name(
    name: str, variants: Iterable[str] | None, canonical_name: str | None = None,
) -> Rule | None:
    forms = {unidecode(value).strip().casefold() for value in (name, *(variants or []), canonical_name) if value}
    return next((rule for rule in RULES if rule.forms & forms), None)
