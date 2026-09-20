"""Bounded OSM address lookup using the verified Łódź response shape."""

from copy import deepcopy
from unittest.mock import MagicMock

import pytest
import requests

from library.address_overpass_client import (
    DEFAULT_OVERPASS_URL,
    REQUEST_TIMEOUT_S,
    find_osm_building_match,
)
from library.overpass_client import USER_AGENT


VERIFIED_RESPONSE = {
    "elements": [{
        "type": "way",
        "id": 106305382,
        "center": {"lat": 51.7486900, "lon": 19.4211182},
        "tags": {
            "addr:city": "Łódź",
            "addr:housename": "blok 31",
            "addr:housenumber": "15",
            "addr:street": "Bratysławska",
            "building": "apartments",
            "building:levels": "11",
            "source:addr": "EMUiA (emuia.geoportal.gov.pl)",
        },
    }],
}
VERIFIED_QUERY = '''[out:json][timeout:20];
(
  node(around:400,51.746111,19.418129)["addr:housenumber"];
  way(around:400,51.746111,19.418129)["addr:housenumber"];
);
out center tags;'''


@pytest.fixture
def external(monkeypatch):
    response = MagicMock()
    response.json.return_value = deepcopy(VERIFIED_RESPONSE)
    response.ok, response.status_code = True, 200
    post = MagicMock(return_value=response)
    config = MagicMock(return_value={})
    events = MagicMock()
    monkeypatch.setattr("library.address_overpass_client.requests.post", post)
    monkeypatch.setattr("library.config_loader.load_config", config)
    monkeypatch.setattr("library.external_service_events.record_external_service_event", events)
    monkeypatch.setattr("library.address_overpass_client._last_request_at", 0)
    return post, config, events


def lookup(street="Bratysławska", number="15"):
    return find_osm_building_match(51.746111, 19.418129, street, number)


@pytest.mark.parametrize("postal_code", [None, "94-039"])
def test_exact_verified_way_match_and_request(external, postal_code):
    post, _, events = external
    if postal_code:
        post.return_value.json.return_value["elements"][0]["tags"]["addr:postcode"] = postal_code
    assert lookup() == {
        "found": True, "lat": 51.7486900, "lon": 19.4211182,
        "postal_code": postal_code, "housename": "blok 31",
        "osm_id": 106305382, "osm_type": "way", "nearby_postal_code": None,
    }
    post.assert_called_once_with(
        DEFAULT_OVERPASS_URL, data={"data": VERIFIED_QUERY},
        headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT_S,
    )
    assert events.call_args.kwargs["service"] == "overpass"
    assert events.call_args.kwargs["operation"] == "address_lookup"


def test_configured_endpoint_and_radius(external):
    post, config, _ = external
    config.return_value = {"OVERPASS_URL": "https://overpass.example/api/interpreter/"}
    find_osm_building_match(51.746111, 19.418129, "Bratysławska", "15", radius_m=200)
    post.assert_called_once_with(
        "https://overpass.example/api/interpreter", data={"data": VERIFIED_QUERY.replace("around:400", "around:200")},
        headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT_S,
    )


@pytest.mark.parametrize("element_type", ["node", "relation"])
def test_coordinate_shapes_and_optional_housename(external, element_type):
    element = external[0].return_value.json.return_value["elements"][0]
    element["type"] = element_type
    if element_type == "node":
        element.update(element.pop("center"))
    del element["tags"]["addr:housename"]
    hit = lookup()
    assert (hit["lat"], hit["lon"], hit["osm_type"]) == (51.7486900, 19.4211182, element_type)
    assert hit["housename"] is None


@pytest.mark.parametrize("street", ["BRATYSLAWSKA", "bratysławska", " Bratysławska "])
def test_street_case_and_polish_diacritics(external, street):
    assert lookup(street=street)["found"] is True


@pytest.mark.parametrize("number,found", [("15a", True), ("15", False), ("015A", False), ("15 A", False)])
def test_building_number_is_case_insensitive_but_not_fuzzy(external, number, found):
    external[0].return_value.json.return_value["elements"][0]["tags"]["addr:housenumber"] = "15A"
    assert lookup(number=number)["found"] is found


@pytest.mark.parametrize("exact_match", [False, True])
@pytest.mark.parametrize("neighbor_first", [False, True])
def test_neighbor_postcode_is_separate_even_when_exact_building_has_none(external, exact_match, neighbor_first):
    elements = external[0].return_value.json.return_value["elements"]
    neighbor = deepcopy(elements[0])
    neighbor["id"] = 123
    neighbor["tags"].update({"addr:housenumber": "17", "addr:postcode": "94-039"})
    if not exact_match:
        elements.clear()
    elements.insert(0 if neighbor_first else len(elements), neighbor)
    hit = lookup()
    assert hit["found"] is exact_match
    assert hit["postal_code"] is None
    assert hit["nearby_postal_code"] == "94-039"
    if exact_match:
        assert hit["osm_id"] == 106305382
        assert hit["housename"] == "blok 31"


@pytest.mark.parametrize("elements", [
    [], [{"tags": {}}],
    [{"tags": {"addr:street": "Inna", "addr:housenumber": "15", "addr:postcode": "94-039"}}],
    [{"tags": {"addr:street": "Bratysławska", "addr:housenumber": "17", "addr:postcode": " "}}],
])
def test_no_match(external, elements):
    external[0].return_value.json.return_value = {"elements": elements}
    assert lookup() == {"found": False, "postal_code": None, "nearby_postal_code": None}


@pytest.mark.parametrize("failure", [requests.ConnectionError(), requests.Timeout(), "http", "json"])
def test_failure_returns_none(external, failure):
    post = external[0]
    if failure == "http":
        post.return_value.raise_for_status.side_effect = requests.HTTPError()
    elif failure == "json":
        post.return_value.json.side_effect = ValueError("invalid JSON")
    else:
        post.side_effect = failure
    assert lookup() is None


@pytest.mark.parametrize("payload", [None, [], {}, {"elements": None}, {"elements": [], "remark": "runtime error: timeout"}])
def test_incomplete_payload_is_unavailable(external, payload):
    external[0].return_value.json.return_value = payload
    assert lookup() is None


@pytest.mark.parametrize("street,number", [(None, "15"), ("Bratysławska", None), (" ", "15"), ("Bratysławska", "")])
def test_missing_address_parts_skip_request(external, street, number):
    assert lookup(street, number) is None
    external[0].assert_not_called()
