"""Best-effort public Wikipedia intros and optional Wikidata context."""

import re
import unicodedata
from difflib import SequenceMatcher

import requests

HEADERS = {"User-Agent": "LenieWorldEvents/1.0"}


def _get(url, **params):
    response = requests.get(url, params=params, headers=HEADERS, timeout=15)
    response.raise_for_status()
    return response.json()


def _normalized(title):
    return " ".join(re.findall(r"\w+", unicodedata.normalize("NFKC", title).casefold()))


def find_article(titles: list[str], langs=("pl", "en")):
    for lang in langs:
        for title in titles:
            try:
                data = _get(
                    f"https://{lang}.wikipedia.org/w/api.php",
                    action="query",
                    generator="search",
                    gsrsearch=title,
                    gsrlimit=3,
                    prop="extracts|pageprops|info",
                    exintro=1,
                    explaintext=1,
                    exchars=1800,
                    inprop="url",
                    format="json",
                    formatversion=2,
                    redirects=1,
                )
                candidates = []
                for page in data.get("query", {}).get("pages", []):
                    if not page.get("extract") or "disambiguation" in page.get("pageprops", {}):
                        continue
                    score = SequenceMatcher(None, _normalized(title), _normalized(page["title"])).ratio()
                    if score >= 0.5 and page.get("fullurl"):
                        candidates.append((score, page))
                if candidates:
                    page = max(candidates, key=lambda item: item[0])[1]
                    return {
                        "lang": lang,
                        "title": page["title"],
                        "url": page["fullurl"],
                        "extract": page["extract"][:1800],
                        "wikidata_id": page.get("pageprops", {}).get("wikibase_item"),
                    }
            except (requests.RequestException, ValueError, TypeError, KeyError, AttributeError):
                continue
    return None


def wikidata_facts(qid, lang="pl"):
    if not isinstance(qid, str) or not re.fullmatch(r"Q[1-9]\d*", qid):
        return {}
    try:
        url = "https://www.wikidata.org/w/api.php"
        data = _get(url, action="wbgetentities", ids=qid, props="claims", format="json")
        claims = data["entities"][qid].get("claims", {})

        def values(prop):
            return [
                c["mainsnak"]["datavalue"]["value"]
                for c in claims.get(prop, [])
                if "datavalue" in c.get("mainsnak", {})
            ]

        dates = {}
        for prop, name in (("P585", "point_in_time"), ("P580", "start"), ("P582", "end")):
            dates[name] = next((v.get("time") for v in values(prop) if isinstance(v, dict)), None)
        ids = [v["id"] for v in values("P17") if isinstance(v, dict) and "id" in v]
        result = {"dates": dates, "country_ids": ids}
        if ids:
            labels = _get(url, action="wbgetentities", ids="|".join(ids), props="labels", languages=lang, format="json")
            result["countries"] = [
                entity["labels"][lang]["value"]
                for entity in labels.get("entities", {}).values()
                if lang in entity.get("labels", {})
            ]
        return result
    except (requests.RequestException, ValueError, TypeError, KeyError, AttributeError):
        return {}
