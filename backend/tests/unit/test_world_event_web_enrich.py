"""Web enrichment is a proposal, never a registry write or an unrequested paid call."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask

from library import web_search_client as client
from library import world_event_web_enrich as service
from library import world_events_routes as routes


@pytest.fixture
def setup(monkeypatch):
    event = {
        "title": "Wybory",
        "aliases": [{"alias": "Wybory testowe"}],
        "event_date": "2026-01-01",
        "description": "",
        "kind": "election",
        "participants": [],
    }
    monkeypatch.setattr(service, "_event", lambda *_: event)
    session = Mock()
    session.scalars.return_value = [SimpleNamespace(slug="polska", name_pl="Polska")]
    monkeypatch.setattr(client, "load_config", lambda: {"SERPER_DEV_APIKEY": "test", "FIRECRAWL_API_KEY": "test"})
    search = Mock(return_value=[{"title": "Wybory", "url": "https://example.org/event", "snippet": "Wybory w Polsce."}])
    monkeypatch.setattr(client, "serper_search", search)
    monkeypatch.setattr(
        client,
        "firecrawl_scrape",
        Mock(return_value={"url": "https://example.org/event", "markdown": "Pełna treść artykułu."}),
    )
    data = {
        "description": "Opis",
        "kind": "election",
        "event_date": "2026-01-01",
        "event_date_end": None,
        "is_ongoing": False,
        "countries": ["Polska"],
        "organizations": ["WHO"],
        "sources_used": [{"url": "https://example.org/event", "quote": "Wybory w Polsce."}],
    }
    answer = SimpleNamespace(response_text=json.dumps(data), usage=None)
    ask = Mock(return_value=answer)
    monkeypatch.setattr(service, "ai_ask", ask)
    return session, data, answer, search, ask


def run(setup):
    return service.enrich(setup[0], 1, model="test", scrape_pages=2, user_id=1, step="web")


def test_happy_path_is_read_only(setup):
    result = run(setup)
    assert result["proposal"]["countries"] == ["polska"]
    assert len(result["proposal"]["sources_used"]) == 1
    assert result["usage"]["firecrawl_credits"] == 1
    assert result["usage"]["llm"]["llm_cost_amount"] is None
    setup[3].assert_called_once_with("Wybory Wybory testowe 2026")
    assert setup[4].call_args.kwargs["operation"] == service.TASK
    assert "document_id" not in setup[4].call_args.kwargs
    setup[0].add.assert_not_called()
    setup[0].commit.assert_not_called()


@pytest.mark.parametrize("wrapper", ["```json\n%s\n```", "Odpowiedź: %s Koniec."])
def test_fences_and_prose(setup, wrapper):
    setup[2].response_text = wrapper % json.dumps(setup[1])
    assert run(setup)["proposal"]["description"] == "Opis"


def test_garbage(setup):
    setup[2].response_text = "no answer"
    assert run(setup)["proposal"] is None


def test_invented_country_and_quote(setup):
    setup[1]["countries"].append("Atlantyda")
    setup[1]["sources_used"].append({"url": "https://example.org/event", "quote": "Nie ma takiego cytatu"})
    setup[1]["sources_used"].append({"url": "https://invented.example/", "quote": "Wybory w Polsce."})
    setup[1]["kind"] = []
    setup[1]["event_date"] = "2026-02-31"
    setup[2].response_text = json.dumps(setup[1])
    result = run(setup)
    assert result["proposal"]["countries"] == ["polska"]
    assert result["rejected"] == {
        "bad_kind": 1,
        "bad_date": 1,
        "unknown_country": 1,
        "quote_not_found": 1,
        "unknown_source": 1,
    }


def test_missing_key_before_spending(setup, monkeypatch):
    monkeypatch.setattr(client, "load_config", lambda: {})
    with pytest.raises(client.WebSearchUnavailable):
        run(setup)
    setup[3].assert_not_called()


@pytest.mark.parametrize(
    "call",
    [
        lambda: client.serper_search("q"),
        client.serper_account,
        lambda: client.firecrawl_scrape("https://example.org"),
        client.firecrawl_credits,
    ],
)
def test_client_missing_key(monkeypatch, call):
    monkeypatch.setattr(client, "load_config", lambda: {})
    with pytest.raises(client.WebSearchUnavailable):
        call()


def test_estimate_has_no_paid_calls(setup, monkeypatch):
    monkeypatch.setattr(service, "model_details", lambda *_: {})
    result = service.estimate(setup[0], 1, model="test", scrape_pages=4, step="web")
    assert result["llm"]["est_cost_usd"] is None
    assert result["firecrawl_credits"] == 4
    setup[3].assert_not_called()
    setup[4].assert_not_called()
    client.firecrawl_scrape.assert_not_called()
    monkeypatch.setattr(
        service,
        "model_details",
        lambda *_: {"input_price_per_million": "1", "output_price_per_million": "2", "currency": "USD"},
    )
    assert service.estimate(setup[0], 1, model="test", scrape_pages=0)["llm"]["est_cost_usd"] is not None


def test_scrape_failure_is_counted(setup, monkeypatch):
    monkeypatch.setattr(client, "firecrawl_scrape", Mock(side_effect=ValueError("bad page")))
    result = run(setup)
    assert result["rejected"]["scrape_failed"] == 1
    assert result["usage"]["firecrawl_credits"] == 0


@pytest.fixture
def http(monkeypatch, setup):
    monkeypatch.setattr(routes, "get_scoped_session", lambda: setup[0])
    monkeypatch.setattr("library.llm_model_registry.is_selectable", lambda m, _: m == "test")
    monkeypatch.setattr(service, "default_model", lambda _: "test")
    app = Flask(__name__)
    app.register_blueprint(routes.bp)
    return app.test_client()


def test_credits_independent(http, monkeypatch):
    monkeypatch.setattr(client, "serper_account", Mock(side_effect=RuntimeError("secret")))
    monkeypatch.setattr(client, "firecrawl_credits", lambda: {"remaining": 20, "plan": 100})
    response = http.get("/web_search/credits")
    assert response.status_code == 200
    assert response.json["serper"]["credits_left"] is None
    assert response.json["firecrawl"]["remaining"] == 20
    assert "secret" not in response.text


@pytest.mark.parametrize("body", [{"model": "bad"}, {"scrape_pages": True}, {"scrape_pages": 5}, []])
def test_bad_request(http, body):
    assert http.post("/geo_events/1/web_enrich", json=body).status_code == 400


def test_missing_key_503(http, monkeypatch):
    monkeypatch.setattr(client, "load_config", lambda: {})
    assert http.post("/geo_events/1/web_enrich", json={"step": "web"}).status_code == 503


def test_unknown_event(http, monkeypatch):
    monkeypatch.setattr(service, "_event", Mock(side_effect=service.GeopoliticsError("Brak", 404)))
    assert http.post("/geo_events/999/web_enrich", json={}).status_code == 404


def test_rest_contracts(monkeypatch):
    monkeypatch.setattr(
        client, "load_config", lambda: {"SERPER_DEV_APIKEY": "serper-test", "FIRECRAWL_API_KEY": "firecrawl-test"}
    )
    post = Mock(
        return_value=Mock(
            json=lambda: {"organic": [{"title": "Title", "link": "https://example.org", "snippet": "Text"}]}
        )
    )
    monkeypatch.setattr(client.requests, "post", post)
    assert client.serper_search("query") == [{"title": "Title", "url": "https://example.org", "snippet": "Text"}]
    assert post.call_args.kwargs == {
        "headers": {"X-API-KEY": "serper-test"},
        "json": {"q": "query", "num": 8, "gl": "pl", "hl": "pl"},
        "timeout": 20,
    }
    post.return_value = Mock(json=lambda: {"success": True, "data": {"markdown": "abcdef"}})
    assert client.firecrawl_scrape("https://example.org", max_chars=3)["markdown"] == "abc"
    assert post.call_args.args[0] == "https://api.firecrawl.dev/v2/scrape"
    assert post.call_args.kwargs["json"] == {
        "url": "https://example.org",
        "formats": ["markdown"],
        "onlyMainContent": True,
    }
    assert post.call_args.kwargs["timeout"] == 20
    get = Mock(return_value=Mock(json=lambda: {"balance": 42}))
    monkeypatch.setattr(client.requests, "get", get)
    assert client.serper_account() == {"credits_left": 42}
    get.return_value = Mock(json=lambda: {"data": {"remainingCredits": 5, "planCredits": 100}})
    assert client.firecrawl_credits() == {"remaining": 5, "plan": 100}
    assert get.call_args.args[0] == "https://api.firecrawl.dev/v2/team/credit-usage"


def test_usage_from_response_and_structured_format(setup, monkeypatch):
    from decimal import Decimal

    setup[2].usage = SimpleNamespace(
        usage_log_id=12,
        total_tokens=100,
        cost=SimpleNamespace(total_cost=Decimal("0.12"), currency="USD", status="reported"),
    )
    monkeypatch.setattr(service, "supports_structured_output", lambda _: True)
    result = run(setup)
    assert result["usage"]["llm"]["llm_cost_amount"] == "0.12"
    assert setup[4].call_args.kwargs["response_format"] == service.RESPONSE_SCHEMA


@pytest.fixture
def wikipedia(setup, monkeypatch):
    article = {
        "lang": "pl",
        "title": "Wybory",
        "url": "https://pl.wikipedia.org/wiki/Wybory",
        "extract": "Wybory w Polsce.",
        "wikidata_id": "Q1",
    }
    monkeypatch.setattr(service.wikipedia_client, "find_article", Mock(return_value=article))
    monkeypatch.setattr(service.wikipedia_client, "wikidata_facts", Mock(return_value={}))
    setup[1]["sources_used"][0]["url"] = article["url"]
    setup[2].response_text = json.dumps(setup[1])
    return article


def test_wikipedia_default_no_paid_keys(setup, wikipedia, monkeypatch):
    monkeypatch.setattr(client, "load_config", lambda: {})
    result = service.enrich(setup[0], 1, model="test", user_id=1)
    assert result["source_step"] == "wikipedia"
    assert result["wikipedia"]["found"] is True
    assert result["usage"]["serper_credits"] == result["usage"]["firecrawl_credits"] == 0
    assert result["proposal"]["sources_used"][0]["url"] == wikipedia["url"]
    setup[3].assert_not_called()
    client.firecrawl_scrape.assert_not_called()
    setup[4].assert_called_once()
    setup[0].commit.assert_not_called()


def test_wikipedia_quote_must_be_in_extract(setup, wikipedia):
    setup[1]["sources_used"][0]["quote"] = "Invented quote"
    setup[2].response_text = json.dumps(setup[1])
    result = service.enrich(setup[0], 1, model="test", user_id=1)
    assert result["proposal"]["sources_used"] == []
    assert result["rejected"]["quote_not_found"] == 1


@pytest.mark.parametrize("timeout", [False, True])
def test_wikipedia_miss_is_free(setup, monkeypatch, timeout):
    from library import wikipedia_client as wiki

    if timeout:
        monkeypatch.setattr(wiki.requests, "get", Mock(side_effect=wiki.requests.Timeout))
    else:
        monkeypatch.setattr(wiki, "find_article", Mock(return_value=None))
    result = service.enrich(setup[0], 1, model="test", user_id=1)
    assert result["proposal"] is None
    assert result["wikipedia"]["found"] is False
    assert result["suggest_web"] is True
    setup[4].assert_not_called()
    setup[3].assert_not_called()


def test_wikipedia_estimate_no_network(setup, monkeypatch):
    find = Mock(side_effect=AssertionError("Unexpected network"))
    monkeypatch.setattr(service.wikipedia_client, "find_article", find)
    monkeypatch.setattr(service, "model_details", lambda *_: {})
    result = service.estimate(setup[0], 1, model="test", scrape_pages=4)
    assert result["serper_credits"] == result["firecrawl_credits"] == 0
    assert result["llm"]["est_input_tokens"] > 450
    setup[3].assert_not_called()
    setup[4].assert_not_called()


@pytest.mark.parametrize("endpoint", ["", "/estimate"])
@pytest.mark.parametrize("step", ["bad", None, [], {}])
def test_unknown_step(http, endpoint, step):
    assert http.post("/geo_events/1/web_enrich" + endpoint, json={"step": step}).status_code == 400


def test_web_wikipedia_context_is_opt_in(setup, wikipedia):
    run(setup)
    service.wikipedia_client.find_article.assert_not_called()
    result = service.enrich(setup[0], 1, model="test", user_id=1, step="web", with_wikipedia=True)
    assert result["wikipedia"]["found"] is True
    assert result["usage"]["firecrawl_credits"] == 1
    assert wikipedia["extract"] in setup[4].call_args.args[0]
    assert result["proposal"]["sources_used"][0]["url"] == wikipedia["url"]


def test_wikipedia_route_needs_no_paid_key(http, wikipedia, monkeypatch):
    monkeypatch.setattr(client, "load_config", lambda: {})
    assert http.post("/geo_events/1/web_enrich", json={}).status_code == 200


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/geo_events/1/web_enrich"),
        ("POST", "/geo_events/1/web_enrich/estimate"),
        ("PUT", "/geo_events/web_enrich/model"),
    ],
)
def test_read_only_guard_blocks_research_and_model_updates(http, method, path):
    from flask import abort, request
    from library.auth import AuthContext, is_read_only_request_allowed

    auth = AuthContext(kind="read_only", key_id=1, key_name="test", user_id=None)

    @http.application.before_request
    def guard():
        if not is_read_only_request_allowed(auth, request.method):
            abort(403)

    assert http.open(path, method=method, json={}).status_code == 403
