"""Unit tests for library.city_gazetteer — non-LLM canonicalization of
well-known single/hyphenated-word foreign city names (rare toponyms spaCy's
Polish lemmatizer can't reliably reduce to nominative).

Pure functions, no LLM/DB calls.
"""

import pytest

pytest.importorskip("unidecode")

from library import city_gazetteer  # noqa: E402


class TestCanonicalCityName:
    @pytest.mark.parametrize(
        "mention",
        ["Omdurman", "Omdurmanie", "Omdurmanu", "Omdurmanem", "Omdurmanowi"],
    )
    def test_matches_every_inflected_form_of_omdurman(self, mention):
        assert city_gazetteer.canonical_city_name(mention) == "Omdurman"

    @pytest.mark.parametrize(
        "mention",
        ["Al-Faszir", "Al-Fasziru", "Al-Faszirze", "Al-Faszirem", "Al Faszirze"],
    )
    def test_matches_hyphenated_and_spaced_al_faszir(self, mention):
        assert city_gazetteer.canonical_city_name(mention) == "Al-Faszir"

    @pytest.mark.parametrize(
        "mention",
        ["Al-Ubajjid", "Al-Ubajid", "Al-Ubajjidzie", "Al-Ubajidzie", "Al Ubajjidem"],
    )
    def test_matches_al_ubajjid_spelling_variants(self, mention):
        assert city_gazetteer.canonical_city_name(mention) == "Al-Ubajjid"

    @pytest.mark.parametrize(
        "mention",
        ["Port Sudan", "Port Sudanu", "Port Sudanem", "Port Sudanie"],
    )
    def test_matches_port_sudan_including_genitive_that_leaks_into_entity_text(self, mention):
        """The real-world bug this fixes: "Port Sudanu"/"Port Sudanem" (genitive/
        instrumental) ended up stored as entity_text verbatim (see doc #9394)."""
        assert city_gazetteer.canonical_city_name(mention) == "Port Sudan"

    def test_unrelated_place_returns_none(self):
        assert city_gazetteer.canonical_city_name("Warszawa") is None

    def test_country_name_is_not_matched_as_a_city(self):
        assert city_gazetteer.canonical_city_name("Sudan") is None

    def test_does_not_search_inside_a_sentence(self):
        assert city_gazetteer.canonical_city_name("Ofensywa RSF na Al-Faszir trwa") is None

    def test_blank_mention_returns_none(self):
        assert city_gazetteer.canonical_city_name("   ") is None
