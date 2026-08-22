"""Unit tests for library/geocode_aliases.py."""

from library.geocode_aliases import geocode_alias


class TestGeocodeAlias:
    def test_known_place_returns_english_transliteration(self):
        assert geocode_alias("Al-Faszir") == "El Fasher"

    def test_unknown_place_returns_none(self):
        assert geocode_alias("Warszawa") is None
