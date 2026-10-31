---
name: 'lenie-contact-linkedin-info'
description: 'Pull structured facts (current city, education, hobby/interest tags) from a contact''s LinkedIn profile via a connected, logged-in browser, and save them to Lenie''s private contact book'
---

Give a contact in Lenie's private contact book (`backend/library/contact_routes.py`) structured facts pulled from their LinkedIn profile: `current_city`, the profile photo (only if the contact has none), education entries (`contact_education`), and hobby/interest tags (`contact_interests`). Useful when a contact is known to have a LinkedIn profile but is missing this data in Lenie.

This is the LinkedIn sibling of [lenie-contact-facebook-enrich](../lenie-contact-facebook-enrich/SKILL.md) — kept as a **separate** skill rather than folded into it because the source site, navigation, and data shape are different enough to not share a workflow: LinkedIn's picture is lower-resolution and sometimes restricted behind a "2nd-degree connection" limited view, so the photo is only taken when the contact has none yet (Step 3b; Facebook's is usually better), LinkedIn doesn't expose `gender`/`birthday` at all, but *does* give a clean, explicitly-labeled Education section — something Facebook only has inconsistently. Run this skill in addition to (not instead of) the Facebook one when a contact has both profiles; run whichever the contact actually has when only one exists.

`current_city`, education, and hobby tags are all **small-talk aids** — concrete, low-effort conversation topics kept as structured fields (not buried in free-text `notes`) so they're easy to scan before a conversation, and (for education/hobby) searchable/filterable across contacts.

## Input

- A reference to the contact: a bare numeric contact ID, or a link like `http://192.168.200.7:3000/contacts/180`.
- Optionally, a LinkedIn profile URL (`https://www.linkedin.com/in/<slug>/`). If not given, look it up on the contact record first (see Step 1) before asking the user.

## Runtime and API configuration

This is the shared procedure for Claude Code and Codex. Read the contact ID/URL and optional profile URL from the user's request or the arguments passed by the Claude command.

Use `LENIE_API_KEY` from the agent environment for the NAS API. Never print it or store it in this repository. If missing, ask the user to configure it; no Claude memory file is needed. Repository paths below are relative to the repository root.

The curl examples below are **Bash examples only**. In PowerShell use `$env:LENIE_API_KEY`, `Invoke-RestMethod`, and UTF-8 JSON bytes. Example:

```powershell
$contactHeaders = @{ 'x-api-key' = $env:LENIE_API_KEY }
$contactBase = 'http://192.168.200.7:5055'
# Set contactId from the user's request.
$contactResult = Invoke-RestMethod -Uri "$contactBase/contacts/$contactId" -Headers $contactHeaders
# Include only values actually found.
$contactPayload = @{ current_city = $cityFound; change_source = 'osint_lookup'; change_note = 'Profile update' } | ConvertTo-Json -Depth 10
Invoke-RestMethod -Method Patch -Uri "$contactBase/contacts/$contactId" -Headers $contactHeaders -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($contactPayload))
```

Adapt other GET/POST/PATCH examples the same way. Inspect response objects directly instead of using the Bash `python3` pipeline.

Check HTTP/tool errors before continuing. After an uncertain write result, read the affected record/list before retrying to avoid duplicate links, education, interests, or photos.

### Browser adapters

- **Claude Code:** use `ToolSearch` to load available `mcp__claude-in-chrome__` tools: `tabs_context_mcp`, `navigate`, `computer`, `find`, `get_page_text`, and `tabs_close_mcp`. Inspect the session with `tabs_context_mcp`, open a task-owned tab, then navigate. `computer` provides screenshots and `zoom` captures; `get_page_text` reads visible text.
- **Codex:** use browser tools exposed in the current session, such as `mcp__cua_repl`, following their initialization and returned documentation. With that tool start with `cua.getState()` alone, then use documented browser/tab APIs to open a task-owned Chrome tab in the connected logged-in profile. Translate navigation, clicks, visible-text reads, screenshots, and cleanup to documented operations. Do not call Claude tool names or invent screenshot/export methods. Follow applicable browser skill instructions.

The user must already be logged into the relevant site. If the required browser/session is unavailable, report what must be connected or logged in and stop the dependent part. Use only documented screenshot/export capabilities. Close only tabs created for this task.

## Workflow

All contact-book calls go to the NAS backend REST API (`http://192.168.200.7:5055`) with header `x-api-key: $LENIE_API_KEY` (service key from the agent environment; see Runtime and API configuration above).

### Step 1: Resolve the contact and the LinkedIn URL

```bash
curl -s -H "x-api-key: $LENIE_API_KEY" "http://192.168.200.7:5055/contacts/<ID>"
curl -s -H "x-api-key: $LENIE_API_KEY" "http://192.168.200.7:5055/contacts/<ID>/education"
curl -s -H "x-api-key: $LENIE_API_KEY" "http://192.168.200.7:5055/contact_interests"
```

Note `current_city`, `notes`, and `interests` (list of `{id, name}`) from the first call. Look at the `links` array for an entry with `link_type: "linkedin"` — that's the profile URL to use (LinkedIn moved off a dedicated `linkedin_url` column onto `contact_links` in PR #680; there is no other place to look).

- If the user supplied a URL and the contact has none stored yet, save it so future runs don't need it repeated:
  ```bash
  curl -s -H "x-api-key: $LENIE_API_KEY" -H "Content-Type: application/json" \
    -X POST "http://192.168.200.7:5055/contacts/<ID>/links" \
    -d '{"link_type": "linkedin", "url": "<url>"}'
  ```
- If neither the user nor the contact record has a URL, ask the user for it — never guess a profile from a name search; LinkedIn has too many same-name accounts and the point of this skill is a confirmed, specific profile.

### Step 2: Open the profile in Chrome

Use the browser adapter above to open the confirmed profile URL in a task-owned tab and take a screenshot.

**A 2nd/3rd-degree connection often gets LinkedIn's limited public-style view**: the name is truncated to first name + last-initial (e.g. "Rafal S."), and the **Experience** section may be missing entirely even when Education/Skills/Publications still show. Don't treat a missing Experience section as a failure — just skip whatever isn't visible and say so in the report; this skill never needs Experience anyway.

### Step 3: Location → `current_city`

The line under the name/headline (format "City, Region, Country", e.g. "Łódź, Łódzkie, Poland") is the profile's self-reported location. Take just the city (first comma-separated segment) as `current_city`. Skip if the line isn't in that recognizable form, or if it's not present.

### Step 3b: Profile photo (only when the contact has no photo)

Skip when Step 1 shows the contact already has a `photo_url` (say so in the report; a photo from the Facebook skill is usually better). Otherwise click the round profile picture so LinkedIn opens its photo viewer (the larger copy), capture exactly the circle to a local file with the active adapter's documented screenshot/export operation (Claude Code: `computer` `zoom` with `save_to_disk: true`; Codex: only what its browser tool documents - if there is no local export, skip the photo and say so), close the viewer (Escape) and look at the saved image. LinkedIn's image URLs carry signed query strings and the JavaScript tool refuses to return them, so a screenshot of the viewer is the supported route.

Upload only a real photo of the person: if the picture is an illustration, logo, cartoon, a group shot or the grey default silhouette, do not upload it - a contact book used to recognise people is misled by it; report "zdjęcie: brak (awatar nie jest zdjęciem)". A fully visible photo with a round crop is fine (the Facebook skill's crops look the same).

```bash
curl -s -H "x-api-key: $LENIE_API_KEY" -X POST -F "photo=@<saved screenshot path>" "http://192.168.200.7:5055/contacts/<ID>/photo"
```

Plain `-F "photo=@<path>"` only (no `;type=` suffix - it breaks curl in Git Bash). The old photo is kept in the photo history, so this is safe even if one exists.

### Step 4: Education section → `contact_education`

Scroll down to the **Education** section (may require scrolling past Activity/About; use the active adapter to read visible page text if the screenshot does not show it — LinkedIn lazy-loads some sections). For each entry, note the institution name, and the degree text if shown (e.g. "Magister (Mgr)", "Inżynier", "Licencjat"). Map to the `contact_education.degree` enum: `licencjat`→`bachelor`, `inżynier`→`engineer`, `magister`/`mgr`→`master`, `doktor`/`phd`→`doctor`, anything else explicit→`other`, nothing shown→omit (never guess a degree from the institution's typical offerings).

For each entry not already in the education list fetched in Step 1 (match by `institution`, case-insensitive):

```bash
curl -s -H "x-api-key: $LENIE_API_KEY" -H "Content-Type: application/json; charset=utf-8" \
  -X POST "http://192.168.200.7:5055/contacts/<ID>/education" \
  --data-binary '{"institution": "<school/university name>", "degree": "<bachelor|engineer|master|doctor|other, or omit>"}'
```

Use a UTF-8 file with `--data-binary @file.json` instead of an inline `-d` string if the institution name has Polish diacritics and you're building the JSON through shell interpolation (confirmed Git-Bash-on-Windows mangling gotcha).

### Step 5: Hobby/interest tags — conservative, from the headline/About text only

LinkedIn has no labeled "hobby" field. The **headline** (the one-paragraph blurb under the name) is sometimes self-authored prose that names real hobbies (e.g. "Po godzinach resetuję głowę w górach i na korcie badmintonowym" → `góry`/`trekking`, `badminton`). Only extract a hobby tag from a sentence like this — a concrete, unambiguous activity the person names as something they personally do — never from Skills, Publications, or Interests-in-Companies/Groups sections (those are professional/networking signals, not hobbies, and LinkedIn's own "Interests" tab lists followed companies/influencers, not personal hobbies — same noise problem as Facebook's page-likes list, see [lenie-contact-facebook-enrich](../lenie-contact-facebook-enrich/SKILL.md) Step 5b).

If nothing in the headline/About reads as a personal hobby statement, skip this step silently.

For each hobby found, check the interest dictionary fetched in Step 1 for a case-insensitive name match before creating a duplicate:

```bash
# Only if no existing contact_interests entry matches (case-insensitive):
curl -s -H "x-api-key: $LENIE_API_KEY" -H "Content-Type: application/json; charset=utf-8" \
  -X POST "http://192.168.200.7:5055/contact_interests" \
  --data-binary '{"name": "<hobby name>"}'

# Then assign (existing or newly-created) interest_id, skip if already assigned:
curl -s -H "x-api-key: $LENIE_API_KEY" -H "Content-Type: application/json" \
  -X POST "http://192.168.200.7:5055/contacts/<ID>/interests" \
  -d '{"interest_id": <id>}'
```

### Step 6: Save `current_city` and verify

If `current_city` was found and differs from what's already on the contact:

```bash
curl -s -H "x-api-key: $LENIE_API_KEY" -H "Content-Type: application/json; charset=utf-8" \
  -X PATCH "http://192.168.200.7:5055/contacts/<ID>" \
  --data-binary '{"current_city": "<city found>", "change_source": "osint_lookup", "change_note": "Uzupełnione z profilu LinkedIn"}'
```

Then verify everything landed:

```bash
curl -s -H "x-api-key: $LENIE_API_KEY" "http://192.168.200.7:5055/contacts/<ID>" \
  | python3 -c "import json,sys; d=json.load(sys.stdin)['contact']; print(d['current_city'], d['interests'])"
curl -s -H "x-api-key: $LENIE_API_KEY" "http://192.168.200.7:5055/contacts/<ID>/education"
```

Close the task-owned browser tab using the active adapter unless the user asked to keep it open.

### Step 7: Report

Tell the user, in Polish: which contact was updated, which structured facts were added (current city, education entries, hobby tags) or already present, and which sections of the profile were missing/hidden (limited-view name, no Experience section, no usable hobby sentence, etc.). Give the test link `http://192.168.200.7:3000/contacts/<id>`.

## Important

- All communication with the user in **Polish**.
- Never scrape or guess at a LinkedIn profile the user hasn't confirmed belongs to the contact.
- This skill only writes to the private contact book (`contacts`, `contact_links`, `contact_education`, `contact_interests`) via the REST API — it never posts, messages, connects, or interacts with anything on LinkedIn itself, only reads the logged-in-visible profile.
- `contact_interests` is a **shared dictionary across the whole contact book** (like `contact_groups`) — creating a new tag affects every contact, not just this one. Always check for a case-insensitive name match before creating one, and keep names generic/reusable.
- Hobby extraction (Step 5) is intentionally conservative — when in doubt whether something is a genuine stated hobby versus networking/professional content, skip it.
- Works one contact at a time; for a batch of contacts, run the workflow once per contact rather than trying to parallelize Chrome tabs against the same logged-in session.
