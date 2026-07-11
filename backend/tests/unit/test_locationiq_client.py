"""Unit tests for library/locationiq_client.py — geocoding + match-quality check."""

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("requests")

import requests  # noqa: E402

from library.locationiq_client import canonical_place_name, geocode, is_plausible_match, _name_similarity  # noqa: E402


HORMUZ_HIT = {"display_name": "Strait of Hormuz, Oman", "lat": "26.44", "lon": "56.20",
              "class": "natural", "type": "strait"}
# Rzeczywisty fałszywy wynik z testu 2026-07-09: zapytanie "Cieśnina Ormuz"
ILAWA_HIT = {"display_name": "Płytka Cieśnina, Iława, Iławski, Warmian-Masurian Voivodeship, Poland",
             "class": "natural", "type": "strait"}
# Rzeczywisty fałszywy wynik z E2E 2026-07-10: zapytanie "Shahed" (dron)
SHAHED_STATION_HIT = {"display_name": "Shahed, Shiraz Health Road, 098, zone 6, Shiraz, Iran",
                      "class": "railway", "type": "station"}
KYIV_HIT = {"display_name": "Kijów, Ukraina", "class": "boundary", "type": "administrative"}


class TestNameSimilarity:
    def test_exact_first_part(self):
        assert _name_similarity("Kijów", "Kijów, Ukraina") == 1.0

    def test_accents_ignored(self):
        assert _name_similarity("Kijow", "Kijów, Ukraina") == 1.0

    def test_unrelated_name_scores_low(self):
        assert _name_similarity("Cieśnina Ormuz", ILAWA_HIT["display_name"]) < 0.75


class TestCanonicalPlaceName:
    def test_inflected_variant_converges_on_canonical_spelling(self):
        """Regresja na realny przypadek (doc 9216): "Kijowa" i "Kijów" dawały dwa tagi."""
        assert canonical_place_name("Kijowa", "Kijów, gmina Otmuchów, powiat nyski, Polska") == "Kijów"
        assert canonical_place_name("Moskwy", "Moskwa, Wyszobór, gmina Płoty, Polska") == "Moskwa"

    def test_truncated_mention_gets_full_name(self):
        assert canonical_place_name("Ankar", "Ankara, Çankaya, Ankara, Central Anatolia Region, Turcja") == "Ankara"

    def test_best_part_not_always_first(self):
        assert canonical_place_name("Pakistan", "Beludżystan, Pakistan") == "Pakistan"

    def test_empty_display_name_falls_back_to_query(self):
        assert canonical_place_name("Kijów", "") == "Kijów"


class TestIsPlausibleMatch:
    def test_accepts_exact_match(self):
        assert is_plausible_match("Strait of Hormuz", HORMUZ_HIT) is True

    def test_rejects_fuzzy_false_positive(self):
        """Regresja na realny przypadek: "Cieśnina Ormuz" -> jezioro pod Iławą."""
        assert is_plausible_match("Cieśnina Ormuz", ILAWA_HIT) is False

    def test_rejects_empty_display_name(self):
        assert is_plausible_match("Kijów", {"class": "place"}) is False

    def test_rejects_non_place_osm_class(self):
        """Regresja na realny przypadek: "Shahed" (dron) -> stacja kolejowa w Szirazie."""
        assert is_plausible_match("Shahed", SHAHED_STATION_HIT) is False

    def test_rejects_missing_osm_class(self):
        assert is_plausible_match("Kijów", {"display_name": "Kijów, Ukraina"}) is False

    def test_accepts_administrative_boundary(self):
        assert is_plausible_match("Kijów", KYIV_HIT) is True


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

    def test_requests_polish_display_names(self):
        """Bez accept-language=pl display_name wraca po angielsku ("Kyiv") i podobieństwo nazw odrzuca "Kijów"."""
        with patch("library.locationiq_client.requests.get", return_value=_response(body=[KYIV_HIT])) as mock_get:
            with patch("library.locationiq_client._api_key", return_value="pk.test"):
                geocode("Kijów")
        assert mock_get.call_args.kwargs["params"]["accept-language"] == "pl,en"

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
