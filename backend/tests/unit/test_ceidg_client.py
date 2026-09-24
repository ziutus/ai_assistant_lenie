"""Unit tests for library/ceidg_client.py — CEIDG API v3 lookup by NIP."""

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("requests")

import requests  # noqa: E402

from library.ceidg_client import (  # noqa: E402
    company_to_organization_fields,
    get_company_by_nip,
    normalize_nip,
)


def _response(status=200, body=None):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = body if body is not None else {}
    resp.raise_for_status.return_value = None
    return resp


KRATON_FIRMA = {
    "nazwa": "KRATON",
    "status": "AKTYWNY",
    "dataRozpoczecia": "2004-01-06",
    "adresDzialalnosci": {
        "ulica": "ul. Reymonta", "budynek": "12", "kod": "95-070", "miasto": "Aleksandrów Łódzki",
    },
    "telefon": "+48 600 827 080",
    "email": "kraton@kraton.pl",
    "www": "kraton.pl",
}


class TestNormalizeNip:
    def test_strips_spaces(self):
        assert normalize_nip("726 175 68 29") == "7261756829"

    def test_strips_dashes(self):
        assert normalize_nip("726-175-68-29") == "7261756829"

    def test_empty_input(self):
        assert normalize_nip("") == ""
        assert normalize_nip(None) == ""


class TestGetCompanyByNip:
    def test_returns_first_match(self):
        with patch("library.ceidg_client.requests.get", return_value=_response(body={"firma": [KRATON_FIRMA]})):
            with patch("library.ceidg_client._api_key", return_value="jwt.test"):
                assert get_company_by_nip("7261756829") == KRATON_FIRMA

    def test_sends_bearer_token_and_clean_nip(self):
        with patch("library.ceidg_client.requests.get", return_value=_response(body={"firma": []})) as mock_get:
            with patch("library.ceidg_client._api_key", return_value="jwt.test"):
                get_company_by_nip("726 175 68 29")
        assert mock_get.call_args.kwargs["params"]["nip"] == "7261756829"
        assert mock_get.call_args.kwargs["headers"]["Authorization"] == "Bearer jwt.test"

    def test_no_api_key_returns_none_without_request(self):
        with patch("library.ceidg_client.requests.get") as mock_get:
            with patch("library.ceidg_client._api_key", return_value=None):
                assert get_company_by_nip("7261756829") is None
        mock_get.assert_not_called()

    def test_empty_nip_returns_none_without_request(self):
        with patch("library.ceidg_client.requests.get") as mock_get:
            with patch("library.ceidg_client._api_key", return_value="jwt.test"):
                assert get_company_by_nip("") is None
        mock_get.assert_not_called()

    def test_401_returns_none(self):
        with patch("library.ceidg_client.requests.get", return_value=_response(status=401)):
            with patch("library.ceidg_client._api_key", return_value="bad-token"):
                assert get_company_by_nip("7261756829") is None

    def test_204_means_clean_miss(self):
        """CEIDG API v3 uses 204 for 'no data matches these criteria'."""
        with patch("library.ceidg_client.requests.get", return_value=_response(status=204)):
            with patch("library.ceidg_client._api_key", return_value="jwt.test"):
                assert get_company_by_nip("0000000000") is None

    def test_404_also_treated_as_miss(self):
        with patch("library.ceidg_client.requests.get", return_value=_response(status=404)):
            with patch("library.ceidg_client._api_key", return_value="jwt.test"):
                assert get_company_by_nip("0000000000") is None

    def test_empty_firma_list_returns_none(self):
        with patch("library.ceidg_client.requests.get", return_value=_response(body={"firma": []})):
            with patch("library.ceidg_client._api_key", return_value="jwt.test"):
                assert get_company_by_nip("7261756829") is None

    def test_request_failure_returns_none(self):
        with patch("library.ceidg_client.requests.get", side_effect=requests.ConnectionError("boom")):
            with patch("library.ceidg_client._api_key", return_value="jwt.test"):
                assert get_company_by_nip("7261756829") is None


class TestCompanyToOrganizationFields:
    def test_maps_name_address_status_contact(self):
        fields = company_to_organization_fields(KRATON_FIRMA)
        assert fields["organization_name"] == "KRATON"
        assert fields["address"] == "ul. Reymonta 12, 95-070 Aleksandrów Łódzki"
        assert fields["is_current"] is True
        assert fields["start_date"] == "2004-01-06"
        assert "tel.: +48 600 827 080" in fields["notes"]
        assert "e-mail: kraton@kraton.pl" in fields["notes"]
        assert "www:" not in fields["notes"]
        assert fields["website"] == "kraton.pl"

    def test_suspended_status_sets_is_current_false(self):
        firma = {**KRATON_FIRMA, "status": "ZAWIESZONY", "dataZawieszenia": "2026-01-01"}
        fields = company_to_organization_fields(firma)
        assert fields["is_current"] is False
        assert fields["suspended_at"] == "2026-01-01"

    def test_deregistered_status_sets_end_date(self):
        firma = {**KRATON_FIRMA, "status": "WYKRESLONY", "dataWykreslenia": "2026-02-02"}
        fields = company_to_organization_fields(firma)
        assert fields["is_current"] is False
        assert fields["end_date"] == "2026-02-02"

    def test_missing_optional_fields_are_omitted(self):
        fields = company_to_organization_fields({"nazwa": "Bare Co"})
        assert fields == {"organization_name": "Bare Co"}

    def test_empty_dict_yields_empty_fields(self):
        assert company_to_organization_fields({}) == {}
