"""Unit tests for library/overpass_client.py — pipeline geometries + cache."""

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("requests")

import requests  # noqa: E402

from library.db.models import InfraGeometry  # noqa: E402
from library.overpass_client import (  # noqa: E402
    MAX_POINTS_PER_LINE,
    OverpassUnavailable,
    _elements_to_lines,
    _simplify,
    attach_document_pipelines,
    fetch_pipeline,
    get_or_fetch_pipeline,
)

BALTIC_WAY = {
    "type": "way",
    "id": 978208595,
    "tags": {"man_made": "pipeline", "name": "Baltic Pipe", "substance": "gas", "wikidata": "Q4852713"},
    "geometry": [{"lat": 55.0, "lon": 15.0}, {"lat": 55.1, "lon": 15.2}, {"lat": 55.2, "lon": 15.4}],
}


def _response(elements):
    resp = MagicMock()
    resp.json.return_value = {"elements": elements}
    resp.raise_for_status.return_value = None
    return resp


class TestFetchPipeline:
    def test_returns_geometry_and_tags(self):
        with patch("library.overpass_client.requests.post", return_value=_response([BALTIC_WAY])):
            with patch("library.overpass_client._overpass_url", return_value="http://ov/api"):
                hit = fetch_pipeline("Baltic Pipe")

        assert hit["name"] == "Baltic Pipe"
        assert hit["substance"] == "gas"
        assert hit["wikidata_qid"] == "Q4852713"
        assert hit["geojson"]["type"] == "MultiLineString"
        assert hit["geojson"]["coordinates"] == [[[15.0, 55.0], [15.2, 55.1], [15.4, 55.2]]]

    def test_no_elements_means_miss(self):
        with patch("library.overpass_client.requests.post", return_value=_response([])):
            with patch("library.overpass_client._overpass_url", return_value="http://ov/api"):
                assert fetch_pipeline("Beludżystan") is None

    def test_request_failure_raises_not_cached_as_miss(self):
        """Awaria transportu (np. 406/timeout) nie może zatruć cache fałszywym missem."""
        with patch("library.overpass_client.requests.post", side_effect=requests.ConnectionError("boom")):
            with patch("library.overpass_client._overpass_url", return_value="http://ov/api"):
                with pytest.raises(OverpassUnavailable):
                    fetch_pipeline("Baltic Pipe")

    def test_sends_identifying_user_agent(self):
        """overpass-api.de odrzuca generyczne UA (live test 2026-07-11: HTTP 406)."""
        with patch("library.overpass_client.requests.post", return_value=_response([BALTIC_WAY])) as mock_post:
            with patch("library.overpass_client._overpass_url", return_value="http://ov/api"):
                fetch_pipeline("Baltic Pipe")
        assert "lenie-ai" in mock_post.call_args.kwargs["headers"]["User-Agent"]

    def test_short_or_quoted_names_rejected_without_request(self):
        with patch("library.overpass_client.requests.post") as mock_post:
            assert fetch_pipeline("dom") is None
            assert fetch_pipeline('Nord "Stream"') is None
        mock_post.assert_not_called()

    def test_relation_members_become_lines(self):
        relation = {
            "type": "relation",
            "tags": {"type": "route", "route": "pipeline", "name": "Przyjaźń"},
            "members": [
                {"type": "way", "geometry": [{"lat": 52.0, "lon": 23.0}, {"lat": 52.1, "lon": 23.5}]},
                {"type": "way", "geometry": [{"lat": 52.1, "lon": 23.5}, {"lat": 52.2, "lon": 24.0}]},
            ],
        }
        with patch("library.overpass_client.requests.post", return_value=_response([relation])):
            with patch("library.overpass_client._overpass_url", return_value="http://ov/api"):
                hit = fetch_pipeline("Przyjaźń")
        assert len(hit["geojson"]["coordinates"]) == 2


class TestGeometryHelpers:
    def test_simplify_caps_points_keeping_endpoints(self):
        points = [[float(i), float(i)] for i in range(1000)]
        out = _simplify(points)
        assert len(out) == MAX_POINTS_PER_LINE
        assert out[0] == [0.0, 0.0]
        assert out[-1] == [999.0, 999.0]

    def test_short_lines_pass_through(self):
        points = [[0.0, 0.0], [1.0, 1.0]]
        assert _simplify(points) == points

    def test_single_point_lines_dropped(self):
        elements = [{"type": "way", "geometry": [{"lat": 1.0, "lon": 1.0}]}]
        assert _elements_to_lines(elements) == []


class TestGetOrFetchPipeline:
    def _session(self, cached=None):
        session = MagicMock()
        session.query.return_value.filter.return_value.one_or_none.return_value = cached
        return session

    def test_cached_row_short_circuits(self):
        cached = MagicMock(spec=InfraGeometry)
        session = self._session(cached)
        with patch("library.overpass_client.fetch_pipeline") as mock_fetch:
            assert get_or_fetch_pipeline(session, "Baltic Pipe") is cached
        mock_fetch.assert_not_called()

    def test_miss_cached_as_unresolved(self):
        session = self._session(None)
        with patch("library.overpass_client.fetch_pipeline", return_value=None):
            row = get_or_fetch_pipeline(session, "Beludżystan")
        assert row.resolved is False
        session.add.assert_called_once()


class TestAttachDocumentPipelines:
    def _entity(self, text, mentions=2, resolved_geocode=None):
        ent = MagicMock()
        ent.entity_text = text
        ent.mention_count = mentions
        ent.geocode = resolved_geocode
        return ent

    def test_skips_geocoder_confirmed_and_unchecked_places(self):
        """Do Overpass idą tylko encje sprawdzone i ODRZUCONE przez geokoder.

        Potwierdzone miejsce punktowe (Kijów) nie jest rurociągiem, a encje
        niesprawdzone (geocode None — kraje albo weryfikacja jeszcze nie
        biegła) nie mogą zalać Overpass setkami nazw z dużego dokumentu.
        """
        session = MagicMock()
        session.query.return_value.filter.return_value.all.return_value = [
            self._entity("Kijów", resolved_geocode=MagicMock(resolved=True)),
            self._entity("Polska", resolved_geocode=None),
        ]
        with patch("library.overpass_client.get_or_fetch_pipeline") as mock_get:
            summary = attach_document_pipelines(session, 42)
        mock_get.assert_not_called()
        assert summary == {"checked": 0, "resolved": []}

    def test_unresolved_entity_checked_and_reported(self):
        session = MagicMock()
        session.query.return_value.filter.return_value.all.return_value = [
            self._entity("Baltic Pipe", resolved_geocode=MagicMock(resolved=False)),
        ]
        row = MagicMock(resolved=True)
        with patch("library.overpass_client.get_or_fetch_pipeline", return_value=row):
            summary = attach_document_pipelines(session, 42)
        assert summary == {"checked": 1, "resolved": ["Baltic Pipe"]}

    def test_overpass_outage_stops_remaining_lookups(self):
        session = MagicMock()
        session.query.return_value.filter.return_value.all.return_value = [
            self._entity("Baltic Pipe", resolved_geocode=MagicMock(resolved=False)),
            self._entity("Nord Stream", resolved_geocode=MagicMock(resolved=False)),
        ]
        with patch("library.overpass_client.get_or_fetch_pipeline",
                   side_effect=OverpassUnavailable("boom")) as mock_get:
            summary = attach_document_pipelines(session, 42)
        assert mock_get.call_count == 1  # po awarii nie dobijamy kolejnych nazw
        assert summary == {"checked": 0, "resolved": []}
