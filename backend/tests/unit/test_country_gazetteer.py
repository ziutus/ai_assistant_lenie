"""Unit tests for library.country_gazetteer — non-LLM country detection.

Pure functions, no LLM/DB calls.
"""

import pytest

pytest.importorskip("unidecode")

from library import country_gazetteer  # noqa: E402


class TestDetectCountries:
    def test_finds_country_by_nominative_name(self):
        found = country_gazetteer.detect_countries("Polska ogłosiła nowy program zbrojeniowy.")
        assert "polska" in [c.slug for c in found]

    def test_finds_country_by_inflected_form(self):
        found = country_gazetteer.detect_countries("Wczoraj prezydent odwiedził Ukrainę i rozmawiał z ministrem.")
        assert "ukraina" in [c.slug for c in found]

    def test_finds_country_by_adjective_form(self):
        found = country_gazetteer.detect_countries("Rosyjska armia wycofała się z regionu.")
        assert "rosja" in [c.slug for c in found]

    def test_handles_irregular_adjective_stem(self):
        # niemiecki dzieli inny rdzeń niż Niemcy (epenteza), wymaga osobnego wariantu
        found = country_gazetteer.detect_countries("Niemiecki rząd zapowiedział zmiany budżetowe.")
        assert "niemcy" in [c.slug for c in found]

    def test_multiword_country_name_matched_as_phrase(self):
        found = country_gazetteer.detect_countries("Korea Północna przeprowadziła kolejny test rakietowy.")
        slugs = [c.slug for c in found]
        assert "korea-polnocna" in slugs
        assert "korea-poludniowa" not in slugs

    def test_no_countries_returns_empty_list(self):
        found = country_gazetteer.detect_countries("To jest zdanie bez żadnego kraju.")
        assert found == []

    def test_result_sorted_by_name(self):
        found = country_gazetteer.detect_countries("Polska i Niemcy podpisały porozumienie.")
        names = [c.name_pl for c in found]
        assert names == sorted(names)

    def test_diacritics_normalized_matching(self):
        # Duży fragment tekstu bez polskich znaków diakrytycznych (np. skopiowany z ASCII źródła)
        found = country_gazetteer.detect_countries("francuski rzad ogłosił nowe sankcje wobec ukrainy")
        slugs = [c.slug for c in found]
        assert "francja" in slugs
        assert "ukraina" in slugs


class TestSlugConvention:
    def test_slug_matches_kraj_prefix_convention(self):
        found = country_gazetteer.detect_countries("Arabia Saudyjska zwiększyła wydobycie ropy.")
        assert any(c.slug == "arabia-saudyjska" for c in found)


class TestCanonicalCountryName:
    @pytest.mark.parametrize("mention", ["Polska", "polska", "polski", "polskiej"])
    def test_matches_one_complete_country_mention(self, mention):
        assert country_gazetteer.canonical_country_name(mention) == "Polska"

    def test_does_not_search_inside_a_sentence(self):
        assert country_gazetteer.canonical_country_name("Rozmowy z Polską") is None

    @pytest.mark.parametrize(
        ("mention", "country"),
        [
            ("Iranem", "Iran"),
            ("Rosjanie", "Rosja"),
            ("Ukraińcami", "Ukraina"),
            ("włoskiej", "Włochy"),
        ],
    )
    def test_accepts_inflection_with_up_to_four_suffix_chars(self, mention, country):
        assert country_gazetteer.canonical_country_name(mention) == country

    def test_rejects_longer_word_that_only_shares_country_stem(self):
        assert country_gazetteer.canonical_country_name("Włoszczowa") is None
