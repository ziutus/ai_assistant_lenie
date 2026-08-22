"""Unit tests for library.geopolitical_region_gazetteer — non-LLM
canonicalization + synthetic centroid lookup for geopolitical/cultural
macro-regions with no reliable LocationIQ geocode.

Pure functions, no LLM/DB/network calls.
"""

import pytest

pytest.importorskip("unidecode")

from library import geopolitical_region_gazetteer  # noqa: E402


class TestCanonicalGeopoliticalRegionName:
    @pytest.mark.parametrize("mention", ["Sahel", "Sahelu", "sahel"])
    def test_matches_sahel_inflected_forms(self, mention):
        """Doc #9394: "na Sahelu" (locative) — LocationIQ's only hit for the
        bare name is a specific Burkina Faso province, correctly rejected by
        is_plausible_match() (name similarity 0.59 < 0.75), leaving the real,
        constantly-discussed transnational region permanently unresolved."""
        assert geopolitical_region_gazetteer.canonical_geopolitical_region_name(mention) == "Sahel"

    @pytest.mark.parametrize(
        "mention",
        ["Bliski Wschód", "Bliskiego Wschodu", "Bliskim Wschodzie", "bliski wschod"],
    )
    def test_matches_bliski_wschod_inflected_forms(self, mention):
        """Live LocationIQ 2026-08-22: "Bliski Wschód" fuzzy-matched a Warsaw
        restaurant of the same name (correctly rejected)."""
        assert geopolitical_region_gazetteer.canonical_geopolitical_region_name(mention) == "Bliski Wschód"

    @pytest.mark.parametrize("mention", ["Kaukaz", "Kaukazu", "Kaukazie"])
    def test_matches_kaukaz_inflected_forms(self, mention):
        """Live LocationIQ 2026-08-22: "Kaukaz" fuzzy-matched (and PASSED
        is_plausible_match) a hamlet of the same name in Mazowieckie, Poland —
        a same-name false positive the similarity check can't catch."""
        assert geopolitical_region_gazetteer.canonical_geopolitical_region_name(mention) == "Kaukaz"

    @pytest.mark.parametrize(
        "mention",
        ["Afryka Subsaharyjska", "Afryki Subsaharyjskiej", "Afryce Subsaharyjskiej"],
    )
    def test_matches_afryka_subsaharyjska_including_palatalized_locative(self, mention):
        """"Afryce" (k -> c palatalization) needs the dedicated "afryc*"
        variant — a plain "afryk*" prefix wildcard can't reach it."""
        assert geopolitical_region_gazetteer.canonical_geopolitical_region_name(mention) == "Afryka Subsaharyjska"

    @pytest.mark.parametrize(
        "mention",
        ["Ameryka Łacińska", "Ameryki Łacińskiej", "Ameryce Łacińskiej"],
    )
    def test_matches_ameryka_lacinska_including_palatalized_locative(self, mention):
        assert geopolitical_region_gazetteer.canonical_geopolitical_region_name(mention) == "Ameryka Łacińska"

    @pytest.mark.parametrize("mention", ["Lewant", "Lewantu", "Lewancie"])
    def test_matches_lewant_including_palatalized_locative(self, mention):
        assert geopolitical_region_gazetteer.canonical_geopolitical_region_name(mention) == "Lewant"

    @pytest.mark.parametrize(
        "mention",
        ["Azja Południowo-Wschodnia", "Azji Południowo-Wschodniej", "azja poludniowo wschodnia"],
    )
    def test_matches_hyphenated_region_name(self, mention):
        assert (
            geopolitical_region_gazetteer.canonical_geopolitical_region_name(mention)
            == "Azja Południowo-Wschodnia"
        )

    def test_does_not_search_inside_a_sentence(self):
        assert geopolitical_region_gazetteer.canonical_geopolitical_region_name("Konflikty w Sahelu narastają") is None

    def test_bare_generic_word_does_not_match(self):
        """"Wschód"/"Afryka" alone (no macro-region qualifier) must not match —
        this gazetteer only normalizes a complete known region name, it never
        matches a fragment of one."""
        assert geopolitical_region_gazetteer.canonical_geopolitical_region_name("Wschód") is None
        assert geopolitical_region_gazetteer.canonical_geopolitical_region_name("Afryka") is None

    def test_unrelated_place_returns_none(self):
        assert geopolitical_region_gazetteer.canonical_geopolitical_region_name("Warszawa") is None

    def test_country_name_is_not_matched_as_a_region(self):
        assert geopolitical_region_gazetteer.canonical_geopolitical_region_name("Sudan") is None

    def test_already_resolvable_regions_are_deliberately_not_listed(self):
        """"Bałkany"/"Maghreb"/"Ameryka Północna" resolve correctly via live
        LocationIQ (verified 2026-08-22) — they're deliberately left off this
        closed list rather than duplicated with a synthetic centroid."""
        assert geopolitical_region_gazetteer.canonical_geopolitical_region_name("Bałkany") is None
        assert geopolitical_region_gazetteer.canonical_geopolitical_region_name("Maghreb") is None
        assert geopolitical_region_gazetteer.canonical_geopolitical_region_name("Ameryka Północna") is None

    def test_blank_mention_returns_none(self):
        assert geopolitical_region_gazetteer.canonical_geopolitical_region_name("   ") is None


class TestGeopoliticalRegionCentroid:
    def test_returns_coordinates_for_canonical_name(self):
        assert geopolitical_region_gazetteer.geopolitical_region_centroid("Sahel") == (15.0, 10.0)

    def test_exact_match_only_no_fuzzy_matching(self):
        """Unlike canonical_geopolitical_region_name(), this is a plain dict
        lookup — callers must pass the already-canonicalized name (same
        convention as geocode_aliases.geocode_alias())."""
        assert geopolitical_region_gazetteer.geopolitical_region_centroid("Sahelu") is None

    def test_unknown_name_returns_none(self):
        assert geopolitical_region_gazetteer.geopolitical_region_centroid("Warszawa") is None
