"""Unit tests for library.region_gazetteer — non-LLM canonicalization of
well-known multiword foreign administrative-region names (states, provinces).

Pure functions, no LLM/DB calls.
"""

import pytest

pytest.importorskip("unidecode")

from library import region_gazetteer  # noqa: E402


class TestCanonicalRegionName:
    @pytest.mark.parametrize(
        "mention",
        [
            "Kordofan Północny",
            "Kordofanu Północnego",
            "Kordofanowi Północnemu",
            "Kordofanem Północnym",
            "kordofan polnocny",
        ],
    )
    def test_matches_every_inflected_form(self, mention):
        """Doc #9394: "stolicą Kordofanu Północnego" (genitive) kept the
        spaCy lemma unchanged, and the mangled string sent to LocationIQ
        returned an unrelated Warsaw waterworks station instead of the
        Sudanese state (correctly rejected by is_plausible_match(), but
        leaving the real place unresolved)."""
        assert region_gazetteer.canonical_region_name(mention) == "Kordofan Północny"

    def test_does_not_search_inside_a_sentence(self):
        assert region_gazetteer.canonical_region_name("Walki w Kordofanie Północnym trwają") is None

    def test_unrelated_place_returns_none(self):
        assert region_gazetteer.canonical_region_name("Warszawa") is None

    def test_country_name_is_not_matched_as_a_region(self):
        assert region_gazetteer.canonical_region_name("Sudan") is None

    def test_blank_mention_returns_none(self):
        assert region_gazetteer.canonical_region_name("   ") is None
