"""Unit tests for library.geo_feature_gazetteer — non-LLM canonicalization of
well-known multiword geographic feature names (seas, straits, gulfs, canals).

Pure functions, no LLM/DB calls.
"""

import pytest

pytest.importorskip("unidecode")

from library import geo_feature_gazetteer  # noqa: E402


class TestCanonicalGeoFeatureName:
    @pytest.mark.parametrize(
        "mention",
        ["Morze Czerwone", "Morza Czerwonego", "Morzu Czerwonym", "Morzem Czerwonym", "morze czerwony"],
    )
    def test_matches_every_inflected_form(self, mention):
        assert geo_feature_gazetteer.canonical_geo_feature_name(mention) == "Morze Czerwone"

    @pytest.mark.parametrize(
        "mention",
        ["Zatoka Perska", "Zatoki Perskiej", "Zatokę Perską", "Zatoce Perskiej"],
    )
    def test_matches_zatoka_including_palatalized_locative(self, mention):
        """"Zatoce Perskiej" (k -> c palatalization) needs the dedicated
        "zatoc*" variant — a plain "zatok*" prefix wildcard can't reach it."""
        assert geo_feature_gazetteer.canonical_geo_feature_name(mention) == "Zatoka Perska"

    @pytest.mark.parametrize(
        "mention",
        ["Cieśnina Ormuz", "Cieśninie Ormuz", "Cieśniny Ormuz"],
    )
    def test_matches_straits_with_named_generic(self, mention):
        assert geo_feature_gazetteer.canonical_geo_feature_name(mention) == "Cieśnina Ormuz"

    def test_bare_feature_name_without_generic_noun_does_not_match(self):
        """"Ormuz" alone (no "Cieśnina"/"cieśnina" in the mention) is a
        different, legitimate NER span (see the reader investigation this
        module followed) — this gazetteer only normalizes case when the
        generic noun is already part of the mention, it never injects one."""
        assert geo_feature_gazetteer.canonical_geo_feature_name("Ormuz") is None

    def test_does_not_search_inside_a_sentence(self):
        assert geo_feature_gazetteer.canonical_geo_feature_name("Zamknięcie Cieśniny Ormuz przez Iran") is None

    def test_unrelated_place_returns_none(self):
        assert geo_feature_gazetteer.canonical_geo_feature_name("Warszawa") is None

    def test_country_name_is_not_matched_as_a_geo_feature(self):
        assert geo_feature_gazetteer.canonical_geo_feature_name("Iran") is None

    def test_blank_mention_returns_none(self):
        assert geo_feature_gazetteer.canonical_geo_feature_name("   ") is None
