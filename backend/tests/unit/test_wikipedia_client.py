from unittest.mock import Mock

import pytest

from library import wikipedia_client as wiki


def page(title="Wybory", **extra):
    return {
        "title": title,
        "fullurl": "https://pl.wikipedia.org/wiki/Wybory",
        "extract": "Wybory w Polsce.",
        "pageprops": {"wikibase_item": "Q1"},
        **extra,
    }


def test_best_match_skips_disambiguation_and_empty_extract(monkeypatch):
    get = Mock(
        return_value=Mock(
            json=lambda: {
                "query": {
                    "pages": [
                        page(pageprops={"disambiguation": ""}),
                        page(extract=""),
                        page("Wybory parlamentarne"),
                        page(),
                    ]
                }
            }
        )
    )
    monkeypatch.setattr(wiki.requests, "get", get)
    assert wiki.find_article(["Wybory"])["title"] == "Wybory"
    assert get.call_args.kwargs["timeout"] == 15
    assert get.call_args.kwargs["headers"] == {"User-Agent": "LenieWorldEvents/1.0"}
    assert get.call_args.kwargs["params"]["redirects"] == 1


def test_redirect_and_language_alias_fallback(monkeypatch):
    get = Mock(
        side_effect=[
            Mock(json=lambda: {}),
            Mock(json=lambda: {}),
            Mock(
                json=lambda: {
                    "query": {"redirects": [{"from": "Election", "to": "Elections"}], "pages": [page("Elections")]}
                }
            ),
        ]
    )
    monkeypatch.setattr(wiki.requests, "get", get)
    result = wiki.find_article(["Election", "Alias"])
    assert result["title"] == "Elections"
    assert result["lang"] == "en"
    assert get.call_count == 3


@pytest.mark.parametrize("payload", [{}, {"query": {"pages": [page("Unrelated subject")]}}])
def test_no_suitable_article(monkeypatch, payload):
    monkeypatch.setattr(wiki.requests, "get", Mock(return_value=Mock(json=lambda: payload)))
    assert wiki.find_article(["Wybory"]) is None


def test_timeout_is_a_miss(monkeypatch):
    monkeypatch.setattr(wiki.requests, "get", Mock(side_effect=wiki.requests.Timeout))
    assert wiki.find_article(["Wybory"]) is None
    assert wiki.wikidata_facts("Q1") == {}


def test_wikidata_dates_and_country_labels(monkeypatch):
    def claim(value):
        return {"mainsnak": {"datavalue": {"value": value}}}

    get = Mock(
        side_effect=[
            Mock(
                json=lambda: {
                    "entities": {
                        "Q1": {
                            "claims": {
                                "P585": [claim({"time": "+2026-01-01T00:00:00Z"})],
                                "P17": [claim({"id": "Q36"})],
                            }
                        }
                    }
                }
            ),
            Mock(json=lambda: {"entities": {"Q36": {"labels": {"en": {"value": "Poland"}}}}}),
        ]
    )
    monkeypatch.setattr(wiki.requests, "get", get)
    result = wiki.wikidata_facts("Q1", "en")
    assert result["dates"]["point_in_time"] == "+2026-01-01T00:00:00Z"
    assert result["country_ids"] == ["Q36"]
    assert result["countries"] == ["Poland"]
    assert get.call_args.kwargs["params"]["languages"] == "en"
