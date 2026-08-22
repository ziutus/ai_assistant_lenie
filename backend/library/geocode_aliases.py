"""English/OSM-transliteration aliases for place names LocationIQ can't
resolve under their Polish spelling (NER stage 3 fallback).

LocationIQ's underlying OSM data indexes a place under whatever
transliteration its contributors used — usually English — not the Polish
exonym Lenie's NER pipeline canonicalizes to (city_gazetteer.py,
geo_feature_gazetteer.py). Querying the wrong transliteration doesn't
reliably produce a clean miss; it can return a low-quality, unrelated hit
that then has to be rejected by locationiq_client.is_plausible_match(). Live
case: "Al-Faszir" (Polish "sz" for the Arabic sound) returned a random alley
in Cairo, because OSM knows the city as "El Fasher"/"Al Fashir" ("sh"/"f") —
see geocode_cache row for doc 9394 in
tmp/ner-place-org-display-names-summary.md.

place_verification._get_or_create_geocode() tries the alias only after the
primary (Polish) query's hit has failed is_plausible_match() — this is a
fallback query, never a replacement. The cached GeocodeCache row stays keyed
by the original NER-canonicalized query, so miejsce-* tags and the displayed
spelling are always built from the Polish name, never the English alias, and
a query is retried through the alias at most once ever (cache-through, same
as the primary query).

Small, closed list — extend only for a specific place confirmed broken
against LocationIQ, not as a general transliteration table.
"""

GEOCODE_ALIASES: dict[str, str] = {
    # Live-verified against LocationIQ 2026-08-22: a country-qualified alias
    # ("El Fasher, Sudan") drags is_plausible_match()'s ratio below its 0.75
    # threshold (query is compared as one string against each display_name
    # part — appending ", Sudan" pulls the best-matching "Al Fasher" part's
    # score from 0.89 to 0.64). The bare city name alone scores 0.89 and
    # still resolves the correct node (OSM place_id 43364335, Sudan).
    "Al-Faszir": "El Fasher",
}


def geocode_alias(canonical_name: str) -> str | None:
    """The English/OSM query to retry when `canonical_name` failed to geocode."""
    return GEOCODE_ALIASES.get(canonical_name)
