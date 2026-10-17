"""Unit tests for library/geocode_aliases.py."""

from unittest.mock import MagicMock, call, patch

import pytest

from library.geocode_aliases import geocode_alias, geocode_country_hint


class TestGeocodeAlias:
    def test_known_place_returns_english_transliteration(self):
        assert geocode_alias("Al-Faszir") == "El Fasher"

    def test_kaliningrad_alias_doc_10872(self):
        """Doc #10872: LocationIQ indexes Kaliningrad as Królewiec."""
        assert geocode_alias("Kaliningrad") == "Królewiec"

    def test_kaliningrad_alias_fallback_doc_10872(self):
        """The correct node fails the original query but resolves via its alias."""
        pytest.importorskip("sqlalchemy")
        pytest.importorskip("requests")
        from library.locationiq_client import is_plausible_match
        from library.place_verification import _get_or_create_geocode

        hit = {
            "place_id": "173147857",
            "display_name": "Królewiec, Obwód królewiecki, Rosja",
            "lat": "54.71", "lon": "20.51", "class": "place", "type": "city",
        }
        assert is_plausible_match("Kaliningrad", hit) is False
        assert is_plausible_match("Królewiec", hit) is True
        session = MagicMock()
        session.query.return_value.filter.return_value.one_or_none.return_value = None

        with patch("library.place_verification.geocode", return_value=hit) as mock_geocode:
            row = _get_or_create_geocode(session, "Kaliningrad")

        assert mock_geocode.call_args_list == [call("Kaliningrad"), call("Królewiec")]
        assert row.resolved is True
        assert row.query == "Kaliningrad"
        assert row.display_name == "Kaliningrad, Obwód królewiecki, Rosja"
        assert (row.lat, row.lon) == ("54.71", "20.51")

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
