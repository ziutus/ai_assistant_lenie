"""Unit tests for library/locationiq_client.py — geocoding + match-quality check."""

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("requests")

import requests  # noqa: E402

from library.locationiq_client import geocode, is_plausible_match, _name_similarity  # noqa: E402


HORMUZ_HIT = {"display_name": "Strait of Hormuz, Oman", "lat": "26.44", "lon": "56.20"}
# Rzeczywisty fałszywy wynik z testu 2026-07-09: zapytanie "Cieśnina Ormuz"
ILAWA_HIT = {"display_name": "Płytka Cieśnina, Iława, Iławski, Warmian-Masurian Voivodeship, Poland"}


class TestNameSimilarity:
    def test_exact_first_part(self):
        assert _name_similarity("Kijów", "Kijów, Ukraina") == 1.0

    def test_accents_ignored(self):
        assert _name_similarity("Kijow", "Kijów, Ukraina") == 1.0

    def test_unrelated_name_scores_low(self):
        assert _name_similarity("Cieśnina Ormuz", ILAWA_HIT["display_name"]) < 0.75


class TestIsPlausibleMatch:
    def test_accepts_exact_match(self):
        assert is_plausible_match("Strait of Hormuz", HORMUZ_HIT) is True

    def test_rejects_fuzzy_false_positive(self):
        """Regresja na realny przypadek: "Cieśnina Ormuz" -> jezioro pod Iławą."""
        assert is_plausible_match("Cieśnina Ormuz", ILAWA_HIT) is False

    def test_rejects_empty_display_name(self):
        assert is_plausible_match("Kijów", {}) is False


def _response(status=200, body=None):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = body if body is not None else []
    resp.raise_for_status.return_value = None
    return resp


class TestGeocode:
    def test_returns_first_hit(self):
        with patch("library.locationiq_client.requests.get", return_value=_response(body=[HORMUZ_HIT])):
            with patch("library.locationiq_client._api_key", return_value="pk.test"):
                assert geocode("Strait of Hormuz") == HORMUZ_HIT

    def test_404_means_clean_miss(self):
        with patch("library.locationiq_client.requests.get", return_value=_response(status=404)):
            with patch("library.locationiq_client._api_key", return_value="pk.test"):
                assert geocode("Xyzzyplugh") is None

    def test_no_api_key_returns_none_without_request(self):
        with patch("library.locationiq_client.requests.get") as mock_get:
            with patch("library.locationiq_client._api_key", return_value=None):
                assert geocode("Kijów") is None
        mock_get.assert_not_called()

    def test_request_failure_returns_none(self):
        with patch("library.locationiq_client.requests.get", side_effect=requests.ConnectionError("boom")):
            with patch("library.locationiq_client._api_key", return_value="pk.test"):
                assert geocode("Kijów") is None

    def test_empty_result_list_returns_none(self):
        with patch("library.locationiq_client.requests.get", return_value=_response(body=[])):
            with patch("library.locationiq_client._api_key", return_value="pk.test"):
                assert geocode("Kijów") is None
