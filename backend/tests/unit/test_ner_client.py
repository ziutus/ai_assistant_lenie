"""Unit tests for library/ner_client.py — NER microservice client + aggregation."""

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("requests")

import requests  # noqa: E402

from library.ner_client import (  # noqa: E402
    ENTITY_TYPES,
    MAX_TEXT_CHARS,
    aggregate_entities,
    extract_entities,
    warmup_async,
)


def _response(entities):
    resp = MagicMock()
    resp.json.return_value = {"entities": entities}
    resp.raise_for_status.return_value = None
    return resp


class TestExtractEntities:
    def test_returns_entities_from_service(self):
        entities = [{"text": "Donald Tusk", "label": "persName", "lemma": "Donald Tusk", "start": 0, "end": 11}]
        with patch("library.ner_client.requests.post", return_value=_response(entities)) as mock_post:
            with patch("library.ner_client._service_url", return_value="http://ner:8090"):
                result = extract_entities("Donald Tusk spotkał się z premierem.")

        assert result == entities
        assert mock_post.call_args.args[0] == "http://ner:8090/ner"

    def test_empty_text_short_circuits(self):
        with patch("library.ner_client.requests.post") as mock_post:
            assert extract_entities("") == []
            assert extract_entities("   ") == []
        mock_post.assert_not_called()

    def test_service_down_returns_empty(self):
        with patch("library.ner_client.requests.post", side_effect=requests.ConnectionError("boom")):
            with patch("library.ner_client._service_url", return_value="http://ner:8090"):
                assert extract_entities("tekst") == []

    def test_invalid_json_returns_empty(self):
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.side_effect = ValueError("not json")
        with patch("library.ner_client.requests.post", return_value=resp):
            with patch("library.ner_client._service_url", return_value="http://ner:8090"):
                assert extract_entities("tekst") == []

    def test_unexpected_payload_shape_returns_empty(self):
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"entities": "oops"}
        with patch("library.ner_client.requests.post", return_value=resp):
            with patch("library.ner_client._service_url", return_value="http://ner:8090"):
                assert extract_entities("tekst") == []

    def test_text_is_truncated(self):
        with patch("library.ner_client.requests.post", return_value=_response([])) as mock_post:
            with patch("library.ner_client._service_url", return_value="http://ner:8090"):
                extract_entities("x" * (MAX_TEXT_CHARS + 500))
        sent = mock_post.call_args.kwargs["json"]["text"]
        assert len(sent) == MAX_TEXT_CHARS


class TestWarmupAsync:
    def test_fires_probe_in_background(self):
        import threading

        called = threading.Event()

        def fake_post(*args, **kwargs):
            called.set()
            return _response([])

        with patch("library.ner_client.requests.post", side_effect=fake_post):
            with patch("library.ner_client._service_url", return_value="http://ner:8090"):
                warmup_async()
                assert called.wait(timeout=2)

    def test_service_down_does_not_raise(self):
        with patch("library.ner_client.requests.post", side_effect=requests.ConnectionError("boom")):
            with patch("library.ner_client._service_url", return_value="http://ner:8090"):
                warmup_async()  # fire-and-forget — nie może rzucić wyjątku


class TestAggregateEntities:
    def test_groups_inflected_variants_by_lemma(self):
        entities = [
            {"text": "Donald Tusk", "label": "persName", "lemma": "Donald Tusk"},
            {"text": "Tuska", "label": "persName", "lemma": "Tusk"},
            {"text": "Tusk", "label": "persName", "lemma": "Tusk"},
        ]
        assert aggregate_entities(entities) == {
            ("persName", "Donald Tusk"): 1,
            ("persName", "Tusk"): 2,
        }

    def test_falls_back_to_surface_text_without_lemma(self):
        entities = [{"text": "Bosfor", "label": "geogName"}]
        assert aggregate_entities(entities) == {("geogName", "Bosfor"): 1}

    def test_filters_unwanted_types(self):
        entities = [
            {"text": "NATO", "label": "orgName", "lemma": "NATO"},
            {"text": "wtorek", "label": "date", "lemma": "wtorek"},
            {"text": "Warszawa", "label": "placeName", "lemma": "Warszawa"},
        ]
        assert aggregate_entities(entities) == {("placeName", "Warszawa"): 1}

    def test_default_types_cover_persons_and_places(self):
        assert ENTITY_TYPES == ("persName", "geogName", "placeName")

    def test_skips_blank_entities(self):
        assert aggregate_entities([{"text": "  ", "label": "persName"}]) == {}
