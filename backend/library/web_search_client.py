"""Small Serper and Firecrawl REST clients. Credentials never leave request headers."""

import requests

from library.config_loader import load_config

SERPER_CREDITS_PER_SEARCH = 1
FIRECRAWL_CREDITS_PER_PAGE = 1
TIMEOUT = 20


class WebSearchUnavailable(RuntimeError):
    """A required search provider has no credentials."""


def require_key(name):
    key = load_config().get(name)
    if not key:
        raise WebSearchUnavailable(f"Wyszukiwanie niedostępne: brak konfiguracji {name}.")
    return key


def serper_search(query, num=8, gl="pl", hl="pl"):
    response = requests.post(
        "https://google.serper.dev/search",
        headers={"X-API-KEY": require_key("SERPER_DEV_APIKEY")},
        json={"q": query, "num": num, "gl": gl, "hl": hl},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    return [
        {"title": row.get("title", ""), "url": row["link"], "snippet": row.get("snippet", "")}
        for row in response.json().get("organic", [])[:num]
        if isinstance(row, dict) and isinstance(row.get("link"), str)
    ]


def firecrawl_scrape(url, max_chars=6000):
    response = requests.post(
        "https://api.firecrawl.dev/v2/scrape",
        headers={"Authorization": f"Bearer {require_key('FIRECRAWL_API_KEY')}"},
        json={"url": url, "formats": ["markdown"], "onlyMainContent": True},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    body = response.json()
    if body.get("success") is False:
        raise ValueError("Firecrawl nie pobrał strony")
    return {"url": url, "markdown": body["data"]["markdown"][:max_chars]}


def serper_account():
    response = requests.get(
        "https://google.serper.dev/account", headers={"X-API-KEY": require_key("SERPER_DEV_APIKEY")}, timeout=TIMEOUT
    )
    response.raise_for_status()
    return {"credits_left": response.json().get("balance")}


def firecrawl_credits():
    response = requests.get(
        "https://api.firecrawl.dev/v2/team/credit-usage",
        headers={"Authorization": f"Bearer {require_key('FIRECRAWL_API_KEY')}"},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    data = response.json().get("data", {})
    return {"remaining": data.get("remainingCredits"), "plan": data.get("planCredits")}
