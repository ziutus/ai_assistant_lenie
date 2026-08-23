---
name: 'lenie-person-lookup'
description: 'Search the public web for information about a named person, using a short description to filter out other people with the same name'
---

Live, one-off web lookup about a real person outside Lenie's collected library (not a document import, not written to any database — see `[[project_osint_people_lookup_idea]]` in memory: this is deliberately kept separate from Lenie's core, which manages a *collected* library rather than live third-party lookups).

## Input

Either:
- a name and a short disambiguating description, e.g. "Adam Wojtysiak, informatyk, mieszka w Łodzi"; or
- a reference to a contact in Lenie's private contact book (`backend/library/contact_routes.py`): a bare numeric contact ID, or a link like `http://192.168.200.7:3000/contacts/1`.

If a description is given directly, use it as-is. If no description is given and no contact reference either, ask for at least one distinguishing detail (profession, city, employer, age range, a shared acquaintance, etc.) before searching — a bare name search is close to useless for common names.

### Resolving a contact ID/link

1. Extract the numeric ID (from the bare number, or the trailing path segment of a `/contacts/<id>` link).
2. Fetch `GET http://192.168.200.7:5055/contacts/<id>` with header `x-api-key: $env:LENIE_API_KEY` (service key, see `[[reference_lenie_api_key]]` in memory).
3. If the contact isn't found (404), tell the user and stop.
4. Build the name from `first_name` + `last_name`, and the disambiguating description from whichever of `position`, `company`, `address` are populated (e.g. `position="Informatyk"`, `address` containing "Łódź" → same query as typing "informatyk, Łódź" by hand). Fall back to `notes` if those are empty.
5. If the fetched record is too sparse to build any disambiguating description, say so and ask the user for more detail rather than searching on the bare name.

Then proceed with the same search flow below regardless of how the name/description were obtained.

## Instructions

1. Run several `WebSearch` queries combining the name with different disambiguating terms from the description (profession, city, employer) — don't rely on a single query. Useful variations: `"<name>" <city>`, `"<name>" <profession>`, `"<name>" linkedin`, `"<name>" <employer>`.
2. Collect every distinct person the searches surface who shares the name. Do not assume the first hit is the right one — common Polish names routinely belong to several unrelated people.
3. For each candidate, check the snippet/page content against **every** clue in the description, not just one. Use `WebFetch` on the most promising pages when a search snippet alone isn't enough to confirm or rule someone out (note: some sites, e.g. LinkedIn, block direct fetches — treat that as inconclusive, not as a match).
4. Filter out people who clearly contradict the description (wrong city, wrong profession) — keep only candidates who are consistent with it or genuinely ambiguous.
5. Present the results in Polish:
   - if one clear match: name, what was found (profession, employer, city, public profile links), and which clues confirmed it;
   - if several plausible candidates remain: list each with what's known and what's still ambiguous — do not pick one arbitrarily;
   - if nothing plausible turns up: say so plainly, don't fabricate details or pad the answer with speculation.
6. Cite sources (URLs) for every factual claim.
7. Do not write anything into Lenie (no document import, no contact update) unless the user explicitly asks afterwards — this skill only searches and reports.

Always respond in Polish.
