"""Unit tests for library/wikidata_client.py — fulltext person search (P31=Q5 filter)."""

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("requests")

import requests  # noqa: E402

from library.wikidata_client import (  # noqa: E402
    normalize_wikipedia_url,
    search_persons,
    wikipedia_url_for_qid,
    wikipedia_urls_for_qids,
)


SEARCH_BODY = {"query": {"search": [{"title": "Q22686"}, {"title": "Q16973370"}]}}

ENTITIES_BODY = {
    "entities": {
        "Q22686": {
            "labels": {"pl": {"value": "Donald Trump"}},
            "descriptions": {"pl": {"value": "45. i 47. prezydent USA"}},
            "sitelinks": {
                "enwiki": {"url": "https://en.wikipedia.org/wiki/Donald_Trump"},
                "plwiki": {"url": "https://pl.wikipedia.org/wiki/Donald_Trump"},
            },
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
            {"qid": "Q22686", "label": "Donald Trump", "description": "45. i 47. prezydent USA",
             "wikipedia_url": "https://pl.wikipedia.org/wiki/Donald_Trump"},
            {"qid": "Q16973370", "label": "Trump", "description": "American professional video game player",
             "wikipedia_url": None},
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


class TestNormalizeWikipediaUrl:
    @pytest.mark.parametrize("raw", [None, "", "   "])
    def test_empty_is_none(self, raw):
        assert normalize_wikipedia_url(raw) is None

    def test_http_becomes_https_and_fragment_dropped(self):
        assert normalize_wikipedia_url(" http://pl.wikipedia.org/wiki/Lech_Wa%C5%82%C4%99sa#Zycie ") == \
            "https://pl.wikipedia.org/wiki/Lech_Wa%C5%82%C4%99sa"

    def test_mobile_host_accepted(self):
        assert normalize_wikipedia_url("https://en.m.wikipedia.org/wiki/NATO") == "https://en.m.wikipedia.org/wiki/NATO"

    @pytest.mark.parametrize("raw", [
        "https://evil.example/wiki/Foo",
        "https://pl.wikipedia.org.evil.example/wiki/Foo",
        "https://evil.example/?u=https://pl.wikipedia.org/wiki/Foo",
        "https://wikipedia.org/wiki/Foo",
        "https://pl.wikipedia.org/",
        "https://pl.wikipedia.org/wiki/",
        "https://pl.wikipedia.org/w/index.php?title=Foo",
        "javascript:alert(1)",
        "ftp://pl.wikipedia.org/wiki/Foo",
    ])
    def test_rejects_non_article_addresses(self, raw):
        with pytest.raises(ValueError):
            normalize_wikipedia_url(raw)

    def test_non_string_rejected(self):
        with pytest.raises(ValueError):
            normalize_wikipedia_url(123)


class TestWikipediaUrlsForQids:
    def test_prefers_polish_and_falls_back_to_english(self):
        body = {"entities": {
            "Q1": {"sitelinks": {"enwiki": {"url": "https://en.wikipedia.org/wiki/A"},
                                 "plwiki": {"url": "https://pl.wikipedia.org/wiki/A"}}},
            "Q2": {"sitelinks": {"enwiki": {"url": "https://en.wikipedia.org/wiki/B"}}},
            "Q3": {"sitelinks": {}},
            "Q4": {"missing": ""},
        }}
        with patch("library.wikidata_client.requests.get", return_value=_response(body)) as mock_get:
            result = wikipedia_urls_for_qids(["Q1", "Q2", "Q3", "Q4"])
        assert result == {"Q1": "https://pl.wikipedia.org/wiki/A", "Q2": "https://en.wikipedia.org/wiki/B"}
        assert mock_get.call_count == 1
        assert mock_get.call_args.kwargs["params"]["ids"] == "Q1|Q2|Q3|Q4"

    def test_ignores_sitelink_pointing_outside_wikipedia(self):
        body = {"entities": {"Q1": {"sitelinks": {"plwiki": {"url": "https://evil.example/wiki/A"}}}}}
        with patch("library.wikidata_client.requests.get", return_value=_response(body)):
            assert wikipedia_url_for_qid("Q1") is None

    def test_batches_of_fifty_and_skips_invalid_ids(self):
        qids = [f"Q{i}" for i in range(1, 121)] + ["not-a-qid"]
        with patch("library.wikidata_client.requests.get", return_value=_response({"entities": {}})) as mock_get:
            wikipedia_urls_for_qids(qids)
        assert mock_get.call_count == 3  # 120 valid ids -> 50 + 50 + 20

    def test_failure_returns_empty(self):
        with patch("library.wikidata_client.requests.get", side_effect=requests.ConnectionError("boom")):
            assert wikipedia_urls_for_qids(["Q1"]) == {}
