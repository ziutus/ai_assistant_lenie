"""Unit tests for library/geocode_aliases.py."""

from library.geocode_aliases import geocode_alias, geocode_country_hint


class TestGeocodeAlias:
    def test_known_place_returns_english_transliteration(self):
        assert geocode_alias("Al-Faszir") == "El Fasher"

    def test_unknown_place_returns_none(self):
        assert geocode_alias("Warszawa") is None


class TestGeocodeCountryHint:
    def test_known_place_returns_country_code(self):
        """Doc #9394: "Kosti" (real Sudanese city) ranks below a Czech castle
        under a bare LocationIQ query — biasing by countrycodes=sd fixes it
        without touching the query text (see place_verification.py)."""
        assert geocode_country_hint("Kosti") == "sd"

    def test_unknown_place_returns_none(self):
        assert geocode_country_hint("Warszawa") is None
