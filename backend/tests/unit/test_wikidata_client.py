"""Unit tests for library/wikidata_client.py — person search with P31=Q5 filter."""

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("requests")

import requests  # noqa: E402

from library.wikidata_client import search_persons  # noqa: E402


SEARCH_BODY = {
    "search": [
        {"id": "Q946", "label": "Donald Tusk", "description": "polski polityk, premier"},
        {"id": "Q999", "label": "Shahed 136", "description": "irański dron"},
    ]
}


def _entities_body(human_qids):
    def claims(qid):
        if qid in human_qids:
            return {"P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q5"}}}}]}
        return {"P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q11446"}}}}]}
    return {"entities": {qid: {"claims": claims(qid)} for qid in ["Q946", "Q999"]}}


def _response(body):
    resp = MagicMock()
    resp.json.return_value = body
    resp.raise_for_status.return_value = None
    return resp


class TestSearchPersons:
    def test_returns_only_humans(self):
        responses = [_response(SEARCH_BODY), _response(_entities_body({"Q946"}))]
        with patch("library.wikidata_client.requests.get", side_effect=responses):
            results = search_persons("Donald Tusk")
        assert results == [{"qid": "Q946", "label": "Donald Tusk", "description": "polski polityk, premier"}]

    def test_no_humans_returns_empty(self):
        responses = [_response(SEARCH_BODY), _response(_entities_body(set()))]
        with patch("library.wikidata_client.requests.get", side_effect=responses):
            assert search_persons("Shahed") == []

    def test_no_search_hits_returns_empty(self):
        with patch("library.wikidata_client.requests.get", return_value=_response({"search": []})) as mock_get:
            assert search_persons("Xyzzyplugh Qwerty") == []
        assert mock_get.call_count == 1  # bez drugiego zapytania o encje

    def test_blank_name_short_circuits(self):
        with patch("library.wikidata_client.requests.get") as mock_get:
            assert search_persons("  ") == []
        mock_get.assert_not_called()

    def test_request_failure_returns_empty(self):
        with patch("library.wikidata_client.requests.get", side_effect=requests.ConnectionError("boom")):
            assert search_persons("Donald Tusk") == []

    def test_sends_user_agent(self):
        with patch("library.wikidata_client.requests.get", return_value=_response({"search": []})) as mock_get:
            search_persons("Donald Tusk")
        assert "lenie-ai" in mock_get.call_args.kwargs["headers"]["User-Agent"]
