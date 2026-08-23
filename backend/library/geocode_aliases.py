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


# ISO 3166-1 alpha-2 country-bias hints for names whose *spelling* is already
# correct but whose bare query loses LocationIQ's ranking to an unrelated,
# more "important" place elsewhere. Live case (doc #9394): "Kosti" (a real
# Sudanese city, White Nile state capital) returns the "Kost" castle in
# Czechia as its top hit (higher `importance`); the castle's OSM class
# ("historic") is correctly rejected by is_plausible_match()'s class
# allowlist, but the query never gets another try.
#
# A text alias (as in GEOCODE_ALIASES) doesn't fit here — the spelling is
# already right, only the ranking needs disambiguating, and appending the
# country to the query text hits the exact scoring bug documented above
# (live-verified 2026-08-23: querying "Kosti, Sudan" DOES return the correct
# "Kosti, Nil Biały, Sudan" administrative boundary, but is_plausible_match()
# then compares the 12-char qualified query against the 5-char "Kosti" part
# and scores 0.59, below threshold). Passing `countrycodes` as a separate
# LocationIQ API parameter (locationiq_client.geocode()) biases the ranking
# without touching the query text, so the plausibility check still compares
# the original, short "Kosti" against the correct hit and scores 1.0.
GEOCODE_COUNTRY_HINTS: dict[str, str] = {
    "Kosti": "sd",
}


def geocode_country_hint(canonical_name: str) -> str | None:
    """ISO 3166-1 alpha-2 country code to bias the retry when `canonical_name`
    failed to geocode and has no (or a failed) GEOCODE_ALIASES entry."""
    return GEOCODE_COUNTRY_HINTS.get(canonical_name)
