"""Unit tests for library/wikidata_client.py — fulltext person search (P31=Q5 filter)."""

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("requests")

import requests  # noqa: E402

from library.wikidata_client import search_persons  # noqa: E402


SEARCH_BODY = {"query": {"search": [{"title": "Q22686"}, {"title": "Q16973370"}]}}

ENTITIES_BODY = {
    "entities": {
        "Q22686": {
            "labels": {"pl": {"value": "Donald Trump"}},
            "descriptions": {"pl": {"value": "45. i 47. prezydent USA"}},
        },
        "Q16973370": {
            "labels": {"en": {"value": "Trump"}},
            "descriptions": {"en": {"value": "American professional video game player"}},
        },
    }
}


def _response(body):
    resp = MagicMock()
    resp.json.return_value = body
    resp.raise_for_status.return_value = None
    return resp


class TestSearchPersons:
    def test_returns_candidates_with_labels_and_descriptions(self):
        responses = [_response(SEARCH_BODY), _response(ENTITIES_BODY)]
        with patch("library.wikidata_client.requests.get", side_effect=responses) as mock_get:
            results = search_persons("Trump")

        assert results == [
            {"qid": "Q22686", "label": "Donald Trump", "description": "45. i 47. prezydent USA"},
            {"qid": "Q16973370", "label": "Trump", "description": "American professional video game player"},
        ]
        # Wyszukiwanie pełnotekstowe z filtrem tylko-ludzie (regresja: goły
        # "Trump" w wbsearchentities nie znajdował Donalda Trumpa)
        assert "haswbstatement:P31=Q5" in mock_get.call_args_list[0].kwargs["params"]["srsearch"]

    def test_english_fallback_for_missing_polish_label(self):
        responses = [_response(SEARCH_BODY), _response(ENTITIES_BODY)]
        with patch("library.wikidata_client.requests.get", side_effect=responses):
            results = search_persons("Trump")
        assert results[1]["label"] == "Trump"  # z labels.en

    def test_no_search_hits_returns_empty(self):
        body = {"query": {"search": []}}
        with patch("library.wikidata_client.requests.get", return_value=_response(body)) as mock_get:
            assert search_persons("Xyzzyplugh Qwerty") == []
        assert mock_get.call_count == 1  # bez drugiego zapytania o encje

    def test_blank_name_short_circuits(self):
        with patch("library.wikidata_client.requests.get") as mock_get:
            assert search_persons("  ") == []
        mock_get.assert_not_called()

    def test_request_failure_returns_empty(self):
        with patch("library.wikidata_client.requests.get", side_effect=requests.ConnectionError("boom")):
            assert search_persons("Donald Trump") == []

    def test_sends_user_agent(self):
        with patch("library.wikidata_client.requests.get", return_value=_response({"query": {"search": []}})) as mock_get:
            search_persons("Donald Trump")
        assert "lenie-ai" in mock_get.call_args.kwargs["headers"]["User-Agent"]
