"""Non-LLM gazetteer of historical states and territories (Jugosławia, ZSRR,
Czechosłowacja, NRD, Prusy...) that no longer exist and therefore have no
current LocationIQ/OSM "place" object behind them.

Without this list such a name geocodes to nothing (or to an unrelated place
that happens to share the name), stays `resolved=false` and renders as a dimmed,
"geocoder did not confirm" chip - indistinguishable from a typo or an NER
error. Like geopolitical_region_gazetteer.py, a name listed here never reaches
the live geocoder: place_verification._get_or_create_geocode() synthesizes an
always-resolved GeocodeCache row (osm_type="historical_state") from the data
below, and keeps the period/successors in `GeocodeCache.raw["historical"]` so
the API and UI can mark the place as historical instead of "confirmed".

Coordinates are an approximate representative point (roughly the capital or
the geographic centre), not a boundary - borders of these states changed over
time. Years are the period of existence of the state under that name.

Small, curated list - extend deliberately, never speculatively.
"""

import re
from dataclasses import dataclass
from functools import lru_cache

from unidecode import unidecode


@dataclass(frozen=True)
class HistoricalState:
    name_pl: str
    variants: tuple[str, ...]
    lat: float
    lon: float
    year_from: int
    year_to: int
    successors: str  # short Polish description of what replaced it

    def info(self) -> dict:
        return {
            "year_from": self.year_from,
            "year_to": self.year_to,
            "successors": self.successors,
        }


# variants: same token-pattern convention as geopolitical_region_gazetteer.py -
# a token ending in "*" matches as a word stem (\bTOKEN\w*), whitespace-separated
# tokens match adjacent words (optionally hyphenated). Patterns are matched
# against diacritic-stripped, lower-cased text.
_HISTORICAL_STATES: tuple[HistoricalState, ...] = (
    HistoricalState(
        "Jugosławia", ("jugoslawi*",), 44.8, 20.5, 1918, 2006,
        "Słowenia, Chorwacja, Bośnia i Hercegowina, Serbia, Czarnogóra, Macedonia Północna, Kosowo",
    ),
    HistoricalState(
        "Związek Radziecki", ("zwiazek radziecki", "zwiazek sowiecki", "zwiazk* radziecki*", "zwiazk* sowieck*", "zsrr", "zsrs"),
        55.75, 37.6, 1922, 1991,
        "Rosja, Ukraina, Białoruś, Litwa, Łotwa, Estonia, Gruzja, Armenia, Azerbejdżan, Mołdawia i republiki Azji Środkowej",
    ),
    HistoricalState(
        "Czechosłowacja", ("czechoslowacj*",), 49.0, 17.0, 1918, 1992,
        "Czechy i Słowacja",
    ),
    HistoricalState(
        "NRD", ("nrd", "niemieck* republik* demokratyczn*"), 52.5, 13.4, 1949, 1990,
        "zjednoczone Niemcy",
    ),
    HistoricalState(
        "Prusy", ("prusy", "prusach", "prusom", "prusami"), 54.7, 20.5, 1701, 1947,
        "Niemcy, Polska, Rosja (obwód królewiecki) i Litwa",
    ),
    HistoricalState(
        "Cejlon", ("cejlon*",), 7.9, 80.7, 1815, 1972,
        "Sri Lanka",
    ),
    HistoricalState(
        "Birma", ("birma", "birmy", "birmie", "birme"), 19.8, 96.1, 1948, 1989,
        "Mjanma",
    ),
    HistoricalState(
        "Zair", ("zair", "zairu", "zairze"), -4.3, 15.3, 1971, 1997,
        "Demokratyczna Republika Konga",
    ),
    HistoricalState(
        "Rodezja", ("rodezj*",), -19.0, 29.2, 1965, 1980,
        "Zimbabwe",
    ),
)


@dataclass(frozen=True)
class _CompiledState:
    state: HistoricalState
    patterns: tuple[re.Pattern, ...]


def _compile_variant(variant: str) -> re.Pattern:
    parts = []
    for token in variant.split():
        if token.endswith("*"):
            parts.append(r"\b" + re.escape(token[:-1]) + r"\w*")
        else:
            parts.append(r"\b" + re.escape(token) + r"\b")
    return re.compile(r"[\s-]+".join(parts))


@lru_cache(maxsize=1)
def _compiled_states() -> tuple[_CompiledState, ...]:
    return tuple(
        _CompiledState(state, tuple(_compile_variant(v) for v in state.variants))
        for state in _HISTORICAL_STATES
    )


def canonical_historical_state_name(mention: str) -> str | None:
    """Canonical Polish name when one mention matches a historical state in full.

    Every pattern must consume the complete normalized mention (inflected forms
    such as "Jugosławii"/"Jugosławię" match through the stem), so an arbitrary
    sentence fragment is never treated as the entity.
    """
    normalized = unidecode(mention).strip().lower()
    if not normalized:
        return None
    matches = {
        compiled.state.name_pl
        for compiled in _compiled_states()
        if any(p.fullmatch(normalized) for p in compiled.patterns)
    }
    return next(iter(matches)) if len(matches) == 1 else None


def historical_state(canonical_name: str) -> HistoricalState | None:
    """Exact lookup by canonical name (as produced by canonical_historical_state_name)."""
    for state in _HISTORICAL_STATES:
        if state.name_pl == canonical_name:
            return state
    return None
