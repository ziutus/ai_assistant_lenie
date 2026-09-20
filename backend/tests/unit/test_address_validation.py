"""Registry validation contract tests; fixtures are documented, not live captures."""

import datetime as dt
import json
from unittest.mock import MagicMock

import pytest
import requests

from library.address_validation import validate_address
from library.address_validation_client import MATCH_URL, validate_address_external
from library.db.models import Address


MATCH = {
    "miejscowosc": "Wrocław", "ulica_norm": "Rynek", "nr_budynku": "1",
    "kod_pocztowy": "50-106", "teryt_simc": "0986283",
    "lat": 51.10893, "lon": 17.03262, "score": 0.98,
}
FOUND = {"results": [{"input": "Rynek 1, Wrocław", "status": "matched", "match": MATCH}]}
PREVIOUS = dt.datetime(2026, 1, 2, 3, 4, 5)


def response(body=FOUND, status=200):
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(body).encode("utf-8")
    return result


@pytest.fixture
def external(monkeypatch):
    config = MagicMock(return_value={})
    get = MagicMock(return_value=response())
    events = MagicMock()
    monkeypatch.setattr("library.config_loader.load_config", config)
    monkeypatch.setattr("library.address_validation_client.requests.get", get)
    monkeypatch.setattr("library.external_service_events.record_external_service_event", events)
    return get, config, events


@pytest.mark.parametrize("key", [None, "test-key"])
def test_confirmed_request_optional_key_and_observability(external, key):
    get, config, events = external
    config.return_value = {"ADRESY_APP_API_KEY": key} if key else {}
    assert validate_address_external("Rynek 1, Wrocław") == {"outcome": "confirmed", "match": MATCH}
    config.assert_called_once_with()
    get.assert_called_once_with(
        MATCH_URL, params={"q": "Rynek 1, Wrocław"},
        headers={"X-API-Key": key} if key else {}, timeout=15,
    )
    event = events.call_args.kwargs
    assert (event["service"], event["operation"], event["success"], event["status_code"]) == (
        "adresy_app", "match", True, 200,
    )


@pytest.mark.parametrize("body", [
    {"results": []}, {"results": [{"status": "not_found"}]},
    {"results": [{"status": "not_found", "match": None}]},
])
def test_registry_miss(external, body):
    external[0].return_value = response(body)
    assert validate_address_external("Nonexistent 999, Wrocław") == {"outcome": "not_found"}


@pytest.mark.parametrize("body", [
    None, [], {}, {"results": None}, {"results": {}}, {"results": [None]},
    {"results": [{"status": "matched"}]}, {"results": [{"status": "matched", "match": {}}]},
    {"results": [{"status": "matched", "match": []}]},
    {"results": [{"status": "ambiguous", "match": MATCH}]},
    {"results": [{"status": "error"}]}, {"results": [{"status": "new_status"}]},
    {"results": [{"status": "not_found", "match": MATCH}]},
    {"results": [FOUND["results"][0], FOUND["results"][0]]},
])
def test_inconclusive_or_malformed_payload_is_unavailable(external, body):
    external[0].return_value = response(body)
    assert validate_address_external("Rynek 1, Wrocław") is None


@pytest.mark.parametrize("failure", [429, 500, 502, 503, 404, "timeout", "connection", "json"])
def test_failures_remain_unavailable_through_domain(external, failure):
    get, _, events = external
    if isinstance(failure, int):
        # Even a body claiming a miss must not override an HTTP failure.
        get.return_value = response({"results": []}, status=failure)
    elif failure == "json":
        get.return_value._content = b"<html>not JSON</html>"
    else:
        get.side_effect = requests.Timeout() if failure == "timeout" else requests.ConnectionError()
    assert validate_address_external("Rynek 1, Wrocław") is None
    for previous in (None, PREVIOUS):
        address = Address(street="Rynek", building_number="1", city="Wrocław", verified_at=previous)
        assert validate_address(MagicMock(), address) == {
            "outcome": "unavailable", "official_postal_code": None,
            "postal_code_matches": None, "score": None,
        }
        assert address.verified_at == previous
    if failure != "json":
        assert events.call_args.kwargs["success"] is False


@pytest.mark.parametrize("stored,official,matches", [
    ("50-106", "50-106", True), (" 50-106\t", " 50-106 ", True),
    ("5 0-106", "50-106", True), ("ab-cde", "AB-CDE", True),
    ("00-001", "50-106", False), (None, "50-106", None),
    ("  ", "50-106", None), ("50-106", None, None), ("50-106", " ", None),
])
def test_postal_comparison_and_canonical_query(monkeypatch, stored, official, matches):
    address = Address(street=" Rynek ", building_number="1", apartment_number="2", city="Wrocław",
                      country="Polska", postal_code=stored, verified_at=PREVIOUS)
    session = MagicMock()
    client = MagicMock(return_value={"outcome": "confirmed", "match": {**MATCH, "kod_pocztowy": official}})
    monkeypatch.setattr("library.address_validation_client.validate_address_external", client)
    before = dt.datetime.now()
    result = validate_address(session, address)
    assert result == {
        "outcome": "confirmed", "official_postal_code": (official or "").strip() or None,
        "postal_code_matches": matches, "score": 0.98,
    }
    locality = " ".join(filter(None, (" ".join((stored or "").split()), "Wrocław")))
    client.assert_called_once_with(f"Rynek 1/2, {locality}")
    assert before <= address.verified_at <= dt.datetime.now()
    assert address.latitude is None and address.longitude is None and address.geocode_id is None
    session.commit.assert_not_called()


@pytest.mark.parametrize("hit", [{"outcome": "not_found"}, None])
@pytest.mark.parametrize("previous", [None, PREVIOUS])
def test_timestamp_only_changes_for_real_answer(monkeypatch, hit, previous):
    address = Address(city="Wrocław", building_number="999", verified_at=previous)
    monkeypatch.setattr("library.address_validation_client.validate_address_external", lambda _: hit)
    before = dt.datetime.now()
    result = validate_address(MagicMock(), address)
    assert result == {"outcome": "not_found" if hit else "unavailable", "official_postal_code": None,
                      "postal_code_matches": None, "score": None}
    if hit:
        assert before <= address.verified_at <= dt.datetime.now()
    else:
        assert address.verified_at == previous


@pytest.mark.parametrize("building", ["2", None, 1, ""])
def test_different_or_missing_house_is_not_confirmation(monkeypatch, building):
    address = Address(city="Wrocław", building_number="1", verified_at=PREVIOUS)
    monkeypatch.setattr("library.address_validation_client.validate_address_external", lambda _: {
        "outcome": "confirmed", "match": {**MATCH, "nr_budynku": building},
    })
    assert validate_address(MagicMock(), address)["outcome"] == "unavailable"
    assert address.verified_at == PREVIOUS


@pytest.mark.parametrize("score", [None, "invalid", {}, True, float("nan"), float("inf")])
def test_invalid_optional_score_is_null(monkeypatch, score):
    monkeypatch.setattr("library.address_validation_client.validate_address_external", lambda _: {
        "outcome": "confirmed", "match": {**MATCH, "score": score},
    })
    result = validate_address(MagicMock(), Address(city="Wrocław", building_number="1"))
    assert result["outcome"] == "confirmed"
    assert result["score"] is None
