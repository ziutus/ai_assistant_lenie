---
name: 'lenie-person-lookup'
description: 'Search the public web (including Polish business registries — CEIDG/KRS) for information about a named person, using a short description to filter out other people with the same name'
---

Live, one-off web lookup about a real person outside Lenie's collected library (see `[[project_osint_people_lookup_idea]]` in memory: this is deliberately kept separate from Lenie's core, which manages a *collected* library rather than live third-party lookups). Nothing is written to any database automatically — see "Saving findings to a contact" below for the one, explicitly user-confirmed exception.

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
6. Note the contact's own `email`/`email_addresses` and any `nip`/company-shaped detail already on file — inputs for the business-registry check below.

Then proceed with the same search flow below regardless of how the name/description were obtained.

## Instructions

1. Run several `WebSearch` queries combining the name with different disambiguating terms from the description (profession, city, employer) — don't rely on a single query. Useful variations: `"<name>" <city>`, `"<name>" <profession>`, `"<name>" linkedin`, `"<name>" <employer>`.
2. Collect every distinct person the searches surface who shares the name. Do not assume the first hit is the right one — common Polish names routinely belong to several unrelated people.
3. For each candidate, check the snippet/page content against **every** clue in the description, not just one. Use `WebFetch` on the most promising pages when a search snippet alone isn't enough to confirm or rule someone out (note: some sites, e.g. LinkedIn, block direct fetches — treat that as inconclusive, not as a match).
4. Filter out people who clearly contradict the description (wrong city, wrong profession) — keep only candidates who are consistent with it or genuinely ambiguous.
5. **Business-registry check (CEIDG/KRS).** Run this whenever the lookup surfaces, or the contact record already has, either: an NIP/company name to verify, or an email address on a domain that is clearly a private company's own (not a public mail provider like gmail.com/onet.pl/wp.pl/hotmail.com/o2.pl):
   - Search CEIDG (`biznes.gov.pl` wyszukiwarka firm) and KRS (e.g. `rejestr.io`, `aleo.com`, `imsig.pl`) for a company matching the domain/NIP/name.
   - **Email-domain heuristic:** a private company domain given as a contact address in a *public* register (CEIDG, KRS, an old public profile, etc.) usually isn't handed to just anyone — it suggests the person has a real, private tie to that firm (owner/co-owner, family member, or an employee using their work mail personally), not necessarily plain employment. Treat this as a lead to report, not a confirmed fact.
   - Corroborate where possible: does the person's known home address match the company's registered address? Does their own CEIDG entry (if they have one) list that domain as its contact email? Report matches and mismatches (e.g. differing surname from a company's named owner) honestly — a mismatch doesn't rule out a family/marriage connection, but don't paper over it.
6. Present the results in Polish:
   - if one clear match: name, what was found (profession, employer, city, public profile links, and any business-registry finding), and which clues confirmed it;
   - if several plausible candidates remain: list each with what's known and what's still ambiguous — do not pick one arbitrarily;
   - if nothing plausible turns up: say so plainly, don't fabricate details or pad the answer with speculation.
7. Cite sources (URLs) for every factual claim, including CEIDG/KRS entries.
8. Do not write anything into Lenie (no document import, no contact update) unless the user explicitly asks afterwards — this skill only searches and reports. See below for the one exception.

## Saving findings to a contact

If the lookup was resolved against a contact ID (see "Resolving a contact ID/link") and turned up a business-registry finding (Step 5), offer to save it — but never write automatically:

1. After presenting the results, ask explicitly (in Polish): "Czy zapisać to powiązanie biznesowe w kartotece kontaktu jako niepotwierdzone (do weryfikacji)?"
2. Only on an explicit yes, save it as a **candidate** row via the REST API — never `status: "confirmed"`, since this skill only did a live search, not a human verification:
   ```powershell
   $headers = @{ 'x-api-key' = $env:LENIE_API_KEY; 'Content-Type' = 'application/json; charset=utf-8' }
   $payload = @{
     org_type          = 'other'   # or 'employment'/'jdg'/'board'/'ownership' if the evidence clearly points that way
     organization_name = '<company name>'
     status             = 'candidate'
     nip                = '<nip, if found>'
     regon              = '<regon, if found>'
     address             = '<registered address, if found>'
     source_url          = '<CEIDG/KRS URL>'
     notes               = '<full reasoning: what was found, the domain-heuristic argument, any corroborating/contradicting detail>'
   } | ConvertTo-Json -Depth 10
   $bytes = [Text.Encoding]::UTF8.GetBytes($payload)
   Invoke-RestMethod -Method Post -Uri "http://192.168.200.7:5055/contacts/<ID>/organizations" -Headers $headers -Body $bytes
   ```
   Write the JSON to a UTF-8 file first and read it back with `[System.IO.File]::ReadAllText(path, [Text.Encoding]::UTF8)` if the payload has Polish diacritics built through string interpolation (known Windows-tooling mojibake gotcha — see `[[feedback_nas_utf8_tooling]]` in memory).
3. Never use `POST /contacts/<id>/lookup_results` with `lookup_type: "email"` — the endpoint's validator only accepts `phone`/`linkedin`/`web` (a DB-level constraint drift lets `email` through directly via SQL, but the API itself will reject it with 400). Use `web` there if a non-organizational finding needs recording instead of `contact_organizations`.
4. After saving, verify with `GET /contacts/<ID>` and give the user the contact link (`http://192.168.200.7:3000/contacts/<ID>`) so they can review/confirm the candidate entry themselves later.

Always respond in Polish.
