---
name: 'lenie-contact-ceidg-lookup'
description: 'Look up a contact''s JDG (sole proprietorship) by NIP via the official CEIDG Hurtownia Danych REST API, and save/refresh the result in Lenie''s private contact book'
---

Give a contact in Lenie's private contact book (`backend/library/contact_routes.py`) verified, up-to-date JDG (jednoosobowa działalność gospodarcza / sole proprietorship) data pulled from the **official CEIDG API** (`dane.biznes.gov.pl`, Hurtownia Danych CEIDG), by NIP — no scraping, no browser. Useful when a contact is known to run a JDG and you have (or can find) their NIP.

This is a REST-only sibling of [lenie-person-lookup](../../../.claude/commands/lenie-person-lookup.md)'s step 5 (business-registry check): that command *searches the public web* for a CEIDG/KRS match when it isn't yet known which company belongs to a person. This skill instead does an *authoritative, structured* lookup once the NIP is already confirmed (e.g. from a business card, an email footer, or a prior web search) — it queries the CEIDG data warehouse directly instead of scraping `aplikacja.ceidg.gov.pl`'s public search UI, which is an old ASP.NET WebForms page that Lenie's own webpage downloader cannot parse into usable text (confirmed via document import, `processing_error_code=ERROR_DOWNLOAD`).

## Why the API, not the public CEIDG website

`https://aplikacja.ceidg.gov.pl/CEIDG/CEIDG.Public.UI/SearchDetails.aspx?Id=...` is JS/viewstate-heavy and not reliably scrapable. The **official CEIDG API** (part of Hurtownia Danych CEIDG i biznes.gov.pl) returns the same public registry data as clean JSON, authenticated with a JWT key.

- **Cost**: free.
- **Who can get a key**: anyone with a Polish Profil Zaufany / mObywatel identity — not limited to registered entrepreneurs.
- **How to register** (one-time, human step — cannot be automated by this skill):
  1. Open the "Wniosek o dostęp do raportów CEIDG" e-service at `biznes.gov.pl` and log in with Profil Zaufany or mObywatel.
  2. Fill in the form and required consents.
  3. Sign the application (Podpis Zaufany or Podpis Kwalifikowany).
  4. A JWT API key arrives by e-mail from the biznes.gov.pl administrator, usually within minutes.
- **Rate limit**: roughly 500 requests/hour (subject to change — check current docs at `dane.biznes.gov.pl` if lookups start failing with a rate-limit error).

If the JWT key is not yet configured (see below), stop and tell the user to complete the registration above — do not attempt to substitute a browser scrape of the public search page instead, since that path is already known to fail.

## Input

- A reference to the contact: a bare numeric contact ID, or a link like `http://192.168.200.7:3000/contacts/123`.
- A NIP, either given directly by the user or already present on the contact's `organizations` entry (`org_type: "jdg"`, field `nip`). If neither is available, ask the user for the NIP — never guess it.

## Runtime and API configuration

Read the contact ID/NIP from the user's request or the arguments passed by the Claude command.

Two separate API keys are used, both from the agent environment — never print either or store them in this repository:

- `LENIE_API_KEY` — Lenie NAS backend (`http://192.168.200.7:5055`), same as every other contact skill.
- `CEIDG_API_KEY` — the JWT issued by `dane.biznes.gov.pl` (see registration steps above). If missing, ask the user to register and set it (e.g. in their PowerShell `$PROFILE`, the same way `LENIE_API_KEY` is configured); no Claude memory file is needed for the key value itself, but note in a `reference` memory *that* this env var exists and how it was obtained, mirroring `reference_lenie_api_key.md`.

The curl examples below are **Bash examples only**. In PowerShell use `$env:LENIE_API_KEY` / `$env:CEIDG_API_KEY`, `Invoke-RestMethod`, and UTF-8 JSON bytes, following the same adaptation pattern as [lenie-contact-linkedin-info](../lenie-contact-linkedin-info/SKILL.md)'s "Runtime and API configuration" section.

## Workflow

### Step 1: Resolve the contact and the NIP

```bash
curl -s -H "x-api-key: $LENIE_API_KEY" "http://192.168.200.7:5055/contacts/<ID>"
```

Look in the `organizations` array for an entry with `org_type: "jdg"`. If it has a `nip`, use it (strip spaces before querying the API: `"726 175 68 29"` → `7261756829`). If no such entry exists yet, or it has no NIP, use the NIP supplied by the user in this request; ask if neither is available.

### Step 2: Query the CEIDG API

```bash
curl -s -H "Authorization: Bearer $CEIDG_API_KEY" \
  "https://dane.biznes.gov.pl/api/ceidg/v2/firmy?nip=<NIP_NO_SPACES>"
```

- A 401/403 means the JWT is missing, expired, or invalid — report this to the user and stop; do not fall back to scraping.
- An empty result (no matching firm) means the NIP is wrong, or the JDG was deregistered and purged from the live registry — report this plainly rather than guessing.
- Inspect the actual JSON shape returned (field names have varied across API versions — check the current response rather than assuming the exact keys below): expect roughly a company name, owner (imię/nazwisko/NIP/REGON), a business address (`adresDzialalnosci`/similar: miejscowość, kod pocztowy, ulica, budynek, lokal), possibly a separate correspondence address (`adresKorespondencyjny`), registration status (aktywny/zawieszony/wykreślony) with relevant dates, and — only if the owner opted to make them public — phone/e-mail/website.

### Step 3: Save/refresh the contact's `organizations` entry

If the contact already has a `jdg` organization entry for this NIP (from Step 1), update it; otherwise create one.

```bash
# Update existing (organization_id from Step 1's organizations array):
curl -s -H "x-api-key: $LENIE_API_KEY" -H "Content-Type: application/json; charset=utf-8" \
  -X PATCH "http://192.168.200.7:5055/contact_organizations/<organization_id>" \
  --data-binary '{
    "organization_name": "<nazwa firmy>",
    "status": "confirmed",
    "address": "<adres działalności>",
    "correspondence_address": "<adres do doręczeń, if different>",
    "notes": "<tel./e-mail/www if publicly listed>",
    "source_url": "https://dane.biznes.gov.pl/api/ceidg/v2/firmy?nip=<NIP_NO_SPACES>",
    "verified_at": "<ISO timestamp, now>"
  }'

# Or create new (no existing jdg entry):
curl -s -H "x-api-key: $LENIE_API_KEY" -H "Content-Type: application/json; charset=utf-8" \
  -X POST "http://192.168.200.7:5055/contacts/<ID>/organizations" \
  --data-binary '{
    "org_type": "jdg",
    "organization_name": "<nazwa firmy>",
    "status": "confirmed",
    "nip": "<NIP formatted as found>",
    "address": "<adres działalności>",
    "correspondence_address": "<adres do doręczeń, if different>",
    "notes": "<tel./e-mail/www if publicly listed>",
    "source_url": "https://dane.biznes.gov.pl/api/ceidg/v2/firmy?nip=<NIP_NO_SPACES>",
    "is_current": true,
    "verified_at": "<ISO timestamp, now>"
  }'
```

If the registry shows the activity as `zawieszona` (suspended) or `wykreślona` (deregistered), reflect that: set `is_current: false` and `suspended_at`/`end_date` from the registry's dates rather than leaving `status: confirmed`/`is_current: true` unchanged — this is exactly the kind of drift a periodic re-check of this skill should catch.

Use a UTF-8 file with `--data-binary @file.json` instead of an inline string if any value has Polish diacritics and you're building the JSON through shell interpolation (confirmed Git-Bash-on-Windows mangling gotcha — see other contact skills).

### Step 4: Verify and report

```bash
curl -s -H "x-api-key: $LENIE_API_KEY" "http://192.168.200.7:5055/contacts/<ID>"
```

Tell the user, in Polish: which contact was updated, what changed vs. what was already stored (new fields filled in, or a discrepancy found — e.g. address changed, activity suspended/deregistered since last check), and the CEIDG registration status. Give the test link `http://192.168.200.7:3000/contacts/<id>`.

## Important

- All communication with the user in **Polish**.
- This skill never guesses a NIP — it either comes from the contact's existing `organizations` entry or from the user.
- Never fall back to scraping `aplikacja.ceidg.gov.pl` if the API key is missing or a call fails — that path is already known to fail (see "Why the API, not the public CEIDG website" above); tell the user instead.
- CEIDG only covers sole proprietorships (JDG). A contact's company that's actually a spółka (sp. z o.o., etc.) needs KRS, not CEIDG — this skill does not handle that case; point the user to [lenie-person-lookup](../../../.claude/commands/lenie-person-lookup.md)'s web-search-based business-registry check instead.
- Works one contact at a time.
