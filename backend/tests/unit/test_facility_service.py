from types import SimpleNamespace

import pytest

pytest.importorskip("sqlalchemy")

from library.facility_service import extract_facility_candidates


def _place(name: str, variants: list[str] | None = None):
    return SimpleNamespace(entity_text=name, variants=variants or [])


def test_extracts_nuclear_power_plant_from_type_and_known_place():
    candidates = extract_facility_candidates(
        "W elektrowni jądrowej Gravelines wyłączono trzy reaktory. "
        "Elektrownia jądrowa Gravelines działa na północy Francji.",
        [_place("Gravelines")],
    )

    assert len(candidates) == 1
    assert candidates[0]["canonical_name"] == "Elektrownia jądrowa Gravelines"
    assert candidates[0]["facility_type"] == "nuclear_power_plant"
    assert candidates[0]["mention_count"] == 2


def test_does_not_turn_a_bare_place_into_facility():
    assert extract_facility_candidates("Gravelines leży na północy Francji.", [_place("Gravelines")]) == []


def test_uses_canonical_place_for_inflected_surface_form():
    candidates = extract_facility_candidates(
        "W elektrowni jądrowej Gravelines doszło do awarii.",
        [_place("Gravelines", ["Gravelines"])],
    )

    assert candidates[0]["canonical_name"] == "Elektrownia jądrowa Gravelines"


def test_merges_bare_power_plant_mention_into_more_specific_nuclear_plant():
    candidates = extract_facility_candidates(
        "Elektrownia jądrowa Gravelines zatrzymała reaktory. "
        "W elektrowni Gravelines trwa przegląd.",
        [_place("Gravelines")],
    )

    assert len(candidates) == 1
    assert candidates[0]["facility_type"] == "nuclear_power_plant"
    assert candidates[0]["mention_count"] == 2
