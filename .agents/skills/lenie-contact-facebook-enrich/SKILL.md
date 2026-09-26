---
name: 'lenie-contact-facebook-enrich'
description: 'Fetch a contact''s current Facebook profile picture and structured facts (current city, hometown, gender, birthday, education, hobby/interest tags) via a connected, logged-in browser, and save them to Lenie''s private contact book'
---

Give a contact in Lenie's private contact book (`backend/library/contact_routes.py`) a profile photo pulled from their Facebook profile picture, plus structured facts from the "Informacje" tab: `current_city` (mieszka w), `hometown` (pochodzi z), `gender`, `birthday`/`birthday_month`/`birthday_day`, education entries (`contact_education`), and hobby/interest tags (`contact_interests`). Useful when a contact is known to have a Facebook profile but is missing this data in Lenie.

Several different motivations drive this, worth keeping straight when deciding what to pull:
- `current_city`/`hometown` are **small-talk aids** — concrete, low-effort conversation topics, kept as their own structured fields (not buried in free-text notes) so they're easy to scan before a conversation.
- `gender` is a **disambiguation aid**, not a small-talk topic — most useful for foreign names/surnames where gender isn't obvious from the name alone and no photo exists yet (real incident that prompted this: a Korean contact's gender was wrongly assumed from the name alone).
- `birthday` is already a first-class field (backs the "Nadchodzące urodziny" view) — this skill is just another way to fill it in when it's visible on Facebook but missing in Lenie.
- Education (`contact_education`, one row per school/university) and hobby tags (`contact_interests`, a shared dictionary M:N with contacts — same pattern as `contact_groups`) are both **small-talk aids** like city/hometown, but structured so they're searchable/filterable across contacts (e.g. "who plays badminton?"), not buried in free-text `notes`.

## Input

- A reference to the contact: a bare numeric contact ID, or a link like `http://192.168.200.7:3000/contacts/180`.
- Optionally, a Facebook profile URL (`https://www.facebook.com/<slug-or-id>`). If not given, look it up on the contact record first (see Step 1) before asking the user.

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

Adapt other GET/POST/PATCH examples the same way. Inspect response objects directly instead of using the Bash `python3` pipeline. For multipart photo upload in PowerShell use `curl.exe` (not the `curl` alias):

```powershell
curl.exe --fail-with-body --silent --show-error -X POST -H "x-api-key: $env:LENIE_API_KEY" -F "photo=@$contactPhotoPath" "$contactBase/contacts/$contactId/photo"
```

Check HTTP/tool errors before continuing. After an uncertain write result, read the affected record/list before retrying to avoid duplicate links, education, interests, or photos.

### Browser adapters

- **Claude Code:** use `ToolSearch` to load available `mcp__claude-in-chrome__` tools: `tabs_context_mcp`, `navigate`, `computer`, `find`, `get_page_text`, and `tabs_close_mcp`. Inspect the session with `tabs_context_mcp`, open a task-owned tab, then navigate. `computer` provides screenshots and `zoom` captures; `get_page_text` reads visible text.
- **Codex:** use browser tools exposed in the current session, such as `mcp__cua_repl`, following their initialization and returned documentation. With that tool start with `cua.getState()` alone, then use documented browser/tab APIs to open a task-owned Chrome tab in the connected logged-in profile. Translate navigation, clicks, visible-text reads, screenshots, and cleanup to documented operations. Do not call Claude tool names or invent screenshot/export methods. Follow applicable browser skill instructions.

The user must already be logged into the relevant site. If the required browser/session is unavailable, report what must be connected or logged in and stop the dependent part. Use only documented screenshot/export capabilities. If a photo cannot be saved locally, report that step as incomplete and continue independently available structured-fact steps. Never upload a fabricated, generated, or unrelated image. Close only tabs created for this task.

## Workflow

All contact-book calls go to the NAS backend REST API (`http://192.168.200.7:5055`) with header `x-api-key: $LENIE_API_KEY` (service key from the agent environment; see Runtime and API configuration above).

### Step 1: Resolve the contact and the Facebook URL

```bash
curl -s -H "x-api-key: $LENIE_API_KEY" "http://192.168.200.7:5055/contacts/<ID>"
```

Note `uuid`, `display_name` (or `first_name`/`last_name`), existing `photo_url`, `current_city`, `hometown`, `gender`, `birthday`/`birthday_month`/`birthday_day`, and `interests` (list of `{id, name}`). Look at the `links` array for an entry with `link_type: "facebook"` — that's the profile URL to use.

Also fetch the contact's existing education entries and the shared interest dictionary, needed later in Step 5:

```bash
curl -s -H "x-api-key: $LENIE_API_KEY" "http://192.168.200.7:5055/contacts/<ID>/education"
curl -s -H "x-api-key: $LENIE_API_KEY" "http://192.168.200.7:5055/contact_interests"
```

- If the user supplied a URL and the contact has none stored yet, save it so future runs don't need it repeated:
  ```bash
  curl -s -H "x-api-key: $LENIE_API_KEY" -H "Content-Type: application/json" \
    -X POST "http://192.168.200.7:5055/contacts/<ID>/links" \
    -d '{"link_type": "facebook", "url": "<url>"}'
  ```
- If neither the user nor the contact record has a URL, ask the user for it — never guess a profile from a name search; Facebook has too many same-name accounts and the point of this skill is a confirmed, specific profile.
- **Recheck gate (90 days):** the same response carries a `lookup_results` array with earlier checks. If it contains a row with `lookup_type: "facebook"` and `searched_at` within the last 90 days, this profile was already checked — report to the user what that run found (`status` + `notes`) and stop, unless the user explicitly asks to force a re-check. Older rows do not block. Only a completed check writes such a row (Step 6b).
- If the contact already has a `photo_url`, mention that a photo already exists and confirm the user wants to replace it before continuing (it isn't destructive — see "Safety net" below — but worth a heads-up).

### Step 2: Open the profile in Chrome and find the current profile picture

Use the browser adapter above.

1. Open the confirmed profile URL in a task-owned tab.
2. **Do not click the small circular avatar directly** — on a profile with family members linked, that hot zone often opens a "Członkowie rodziny" (family members) popup instead of the photo. The reliable path is via the album:
   - Click the **Zdjęcia** tab.
   - Click the **Albumy** sub-tab.
   - Click the **"Zdjęcia profilowe"** album thumbnail.
   - Click the first (most recent / currently-active) photo in that album to open the full-size photo lightbox.
3. Take a screenshot to see the lightbox layout and confirm the photo shown is a real, current profile picture (check the caption/date if visible) and that it's actually of the expected person, not a placeholder or a group photo.

If the "Zdjęcia profilowe" album is empty, private, or doesn't exist (privacy settings vary per profile), fall back to a tightly bounded screenshot capture of the small circular avatar on the main profile page instead — lower resolution, but better than nothing. Tell the user the source was lower-quality when reporting back.

A grey silhouette avatar with an empty photo section means the person has no photo — do not upload the placeholder; record "zdjęcie: brak" in Step 6b.

### Step 3: Capture the photo as a local file

Capture displayed photo pixels with the active browser adapter. Do not extract signed CDN tokens or work around blocked URL access. Claude in Chrome may block signed Facebook image URLs; use its pixel capture:

```text
computer(action: "zoom", tabId: <id>, region: [x0, y0, x1, y1], save_to_disk: true)
```

Choose coordinates from a fresh screenshot to tightly bound the photo pane, excluding comments and unrelated people. The Claude response supplies a temporary local path. In Codex use only the active tool's documented screenshot/export operation; the Claude parameters above do not apply. Verify the local capture visually before upload. If no supported local export exists, skip upload and report the limitation while continuing Step 5.

### Step 4: Upload to the contact

```bash
curl -s -X POST -H "x-api-key: $LENIE_API_KEY" \
  -F "photo=@<saved-path>" \
  "http://192.168.200.7:5055/contacts/<ID>/photo"
```

**Gotcha:** don't add a `;type=image/png` suffix to the `-F` value — in Git Bash this reproducibly makes curl fail with exit code 26 (`Failed to read local file`) even though the file exists and is readable. Plain `-F "photo=@<path>"` works; the server infers/accepts the type fine without it.

A successful response echoes back the new `storage_key` and a presigned `photo_url`.

### Step 5: Pull structured facts from the "Informacje" tab

While still on the profile, visit these sub-pages of the "Informacje" tab (still under the same profile — append the path or click through the tab's left-hand menu):

- `<profile_url>/about_places` (**Miejsca, w których mieszkał(a)**):
  - **"Obecne miasto"** / "Mieszka w" → `current_city`
  - **"Rodzinne miasto"** → `hometown`
- `<profile_url>/about_contact_and_basic_info` (**Kontakt i podstawowe informacje**):
  - **"Płeć"** → `gender` (map "Kobieta" → `female`, "Mężczyzna" → `male`, anything else/custom → `other`)
  - **"Data urodzenia"** → `birthday` if a full date (year included) is shown, otherwise `birthday_month`+`birthday_day` if only day/month is visible (Facebook often hides the year even when the day/month is public) — never guess a missing year
- `<profile_url>/about_work_and_education` (**Praca i edukacja**): each listed school/university entry → an education record. Note the institution name and, if Facebook shows one, the field of study (Facebook rarely states a formal degree level — leave `degree` unset unless the text explicitly names one, e.g. "magister"/"inżynier"; never infer a degree from the institution type alone).

Use the active adapter to read the values on each page from a screenshot or visible page text — this is plain visible text, not blocked like the CDN image URLs in Step 3. Only take a value that is explicitly labeled; don't infer a city, gender, birthday, or school from an unrelated post, check-in, or profile picture caption.

**Current Facebook layout (verified 2026-09):** the `about_*` paths above often show only the profile overview. The "Informacje" left menu links to `<profile_url>/directory_personal_details` (location "Aktualne miejsce zamieszkania" → `current_city`, Płeć, Data urodzenia), `<profile_url>/directory_education` and `<profile_url>/directory_work`; for numeric-id profiles use `profile.php?id=<id>&sk=directory_personal_details`. The right-hand panel loads lazily — wait ~8 s before `get_page_text`/screenshot, and on profiles with an "Osoby, które możesz znać" carousel scroll down to reach it. If the left menu has no "Wykształcenie" entry, the person shares no education — treat it as missing, don't retry.

Skip whichever sub-section is empty or hidden by the profile's privacy settings (say so in the report), and skip the whole step if the profile has no "Informacje" tab visible while logged in as this account.

**Name check:** the profile header (visible on the main page) shows the person's full name. If the contact's `last_name` is empty and the Facebook name clearly matches the contact's first name/`display_name`, take the surname from the header as `last_name` (and `first_name` if that is empty too). Never overwrite an existing non-empty `first_name`/`last_name` — if Facebook's name differs from what's stored (maiden name, nickname, diminutive), flag it to the user instead of changing it.

If any value is found and differs from what's already on the contact (from Step 1), save it in one PATCH call:

```bash
curl -s -H "x-api-key: $LENIE_API_KEY" -H "Content-Type: application/json; charset=utf-8" \
  -X PATCH "http://192.168.200.7:5055/contacts/<ID>" \
  --data-binary '{"current_city": "<current city found>", "hometown": "<hometown found>", "gender": "<male|female|other>", "birthday_month": <1-12>, "birthday_day": <1-31>, "change_source": "osint_lookup", "change_note": "Uzupełnione z zakładki Informacje na Facebooku"}'
```

Only include the keys you actually found (omit the rest entirely rather than sending an empty string/null, which would clear an existing value). `birthday_month`/`birthday_day` must be sent together — see `_validate_birthday_pair()` in `contact_routes.py`. Use a UTF-8 file with `--data-binary @file.json` instead of an inline `-d` string if any value contains Polish diacritics and you're building the JSON through shell interpolation (confirmed gotcha: inline `-d '...Łódź...'` in Git Bash on Windows silently mangles diacritics to ASCII).

For each education entry found that isn't already in the list fetched in Step 1 (match by `institution` name, case-insensitive), add it separately:

```bash
curl -s -H "x-api-key: $LENIE_API_KEY" -H "Content-Type: application/json; charset=utf-8" \
  -X POST "http://192.168.200.7:5055/contacts/<ID>/education" \
  --data-binary '{"institution": "<school/university name>", "field_of_study": "<if shown, else omit>"}'
```

### Step 5b: Hobby/interest tags (conservative — from self-described text only)

Facebook has no clean, explicitly-labeled "hobby" field. Do **not** derive hobby tags from the "Lubię to" / liked-Pages list — that's noisy (brands, media outlets, meme pages), not a curated statement of the person's own interests, and would pollute the shared `contact_interests` dictionary with junk that other contacts then have to wade through.

Instead, only take hobby tags from **prose the person wrote about themselves**: the profile's own bio/intro text on the main page (visible in the Step 2 screenshot, under the name — the same kind of self-authored blurb we already read as a LinkedIn headline in the sibling [lenie-contact-linkedin-info](../lenie-contact-linkedin-info/SKILL.md) skill), or an explicit "Zainteresowania"/custom-field entry if the profile has one. Extract only concrete, unambiguous nouns the person names as something they do (e.g. "biegam, gram w badmintona" → `bieganie`, `badminton`) — never a vague adjective or a business/brand mention from that same bio.

If nothing in the bio reads as a personal hobby statement, skip this step silently — most profiles won't have anything usable here, and that's expected, not a failure.

For each hobby found, check the interest dictionary fetched in Step 1 for a case-insensitive name match before creating a duplicate tag:

```bash
# Only if no existing contact_interests entry matches (case-insensitive):
curl -s -H "x-api-key: $LENIE_API_KEY" -H "Content-Type: application/json; charset=utf-8" \
  -X POST "http://192.168.200.7:5055/contact_interests" \
  --data-binary '{"name": "<hobby name>"}'

# Then assign (existing or newly-created) interest_id to the contact, skip if already assigned:
curl -s -H "x-api-key: $LENIE_API_KEY" -H "Content-Type: application/json" \
  -X POST "http://192.168.200.7:5055/contacts/<ID>/interests" \
  -d '{"interest_id": <id>}'
```

### Step 5c: Links the person published in their own profile (OSINT)

Links the person put there themselves — Instagram, LinkedIn, X/Twitter, a personal or company website — can appear in three places:

- the profile intro under the name on the main page (in `get_page_text` a bare URL line, e.g. `https://www.instagram.com/<handle>/`);
- the **"Linki"** entry of the left "Informacje" menu, present on some profiles (`<profile_url>/directory_links`; shows e.g. `georgiaadventureclub.com` with the label "Strona internetowa" — no scheme, add `https://`);
- the **"Informacje kontaktowe"** entry (`<profile_url>/directory_contact_info`), which usually lists messenger handles (Skype, Gadu-Gadu) rather than URLs — those have no `link_type`, so only mention them in the Step 6b `notes`.

These are self-published leads, so save the URLs on the contact.

- **Only self-published links.** Take URLs from the profile's own intro/bio or its contact-info section. Never from posts, comments, liked pages, "Obserwowani" lists or friends' profiles.
- **Map host → `link_type`:** `instagram.com` → `instagram`; `linkedin.com/in/…` → `linkedin`; `x.com`/`twitter.com` → `twitter`; another personal/company site → `website`; anything else → `other`. Skip Facebook itself (Step 1 already handles the profile URL).
- **Normalize:** strip tracking parameters (`fbclid`, `hl`, `igsh`, `utm_*`), keep host + path, use the visible URL text rather than a `l.facebook.com` redirect.
- **Dedupe** against the `links` array read in Step 1 (case-insensitive host + path); skip what is already there.
- **Save** each new link:
  ```bash
  curl -s -H "x-api-key: $LENIE_API_KEY" -H "Content-Type: application/json; charset=utf-8" \
    -X POST "http://192.168.200.7:5055/contacts/<ID>/links" \
    --data-binary '{"link_type": "instagram", "url": "https://www.instagram.com/<handle>/", "label": "Instagram (z opisu profilu na Facebooku)"}'
  ```
- **Do not follow the link and do not collect data from the target site here.** If reading the profile opens the linked site in a new browser tab (this happened once with an Instagram link), close that tab. Enriching a contact from LinkedIn is the separate `lenie-contact-linkedin-info` skill.
- Mention added links in the Step 6b `notes` line (e.g. `linki: instagram (dodano)`).

### Step 6: Verify and clean up

```bash
curl -s -H "x-api-key: $LENIE_API_KEY" "http://192.168.200.7:5055/contacts/<ID>" \
  | python3 -c "import json,sys; d=json.load(sys.stdin)['contact']; print(d['photo_url'], d['current_city'], d['hometown'], d['gender'], d['birthday'], d['birthday_month'], d['birthday_day'], d['interests'])"
curl -s -H "x-api-key: $LENIE_API_KEY" "http://192.168.200.7:5055/contacts/<ID>/education"
```

If a photo was uploaded, confirm `photo_url` is non-null and the returned storage key identifies the new upload. Confirm the other fields (including `interests` and the education list) reflect what was found (or are unchanged if Step 5/5b found nothing new). Delete the temporary screenshot file(s) from the OS temp dir. Close the task-owned browser tab using the active adapter unless the user asked to keep it open.

### Step 6b: Record the check (also when nothing was found)

Write one `contact_lookup_results` row per completed check, so the same profile is not scraped again within 90 days (Step 1 gate):

```bash
curl -s -H "x-api-key: $LENIE_API_KEY" -H "Content-Type: application/json; charset=utf-8" \
  -X POST "http://192.168.200.7:5055/contacts/<ID>/lookup_results" \
  --data-binary @lookup.json   # {"lookup_type": "facebook", "status": "confirmed|no_results", "url": "<profile url>", "notes": "<one line>"}
```

- `status: confirmed` when at least one field, education entry or photo was saved or was already present and matches; `no_results` when the profile gave nothing usable (empty or private "Informacje", placeholder avatar).
- `notes`: one line listing what was found and what was missing, with the reason where known — e.g. `znaleziono: płeć, miasto, 2 szkoły, zdjęcie; brak: miejsce pochodzenia (nie udostępnione), urodziny (ukryte), wykształcenie (brak w menu), hobby`.
- Do not write a row when the check could not complete (not logged in, page failed to load, blocked by Facebook) — an incomplete run must not suppress a retry.
- Use a UTF-8 file with `--data-binary @file`, as for the other calls with Polish text.

### Step 7: Report

Tell the user, in Polish: which contact was updated, where the photo came from (profile URL, which album/photo), and which structured facts (if any) were added or already present — including education entries, hobby tags (or a note that Step 5b found nothing usable) and any profile links added in Step 5c. Give the test link `http://192.168.200.7:3000/contacts/<id>`.

## Safety net: photo history

Uploading never deletes a previous photo — every upload mints a new immutable storage key (previous versions are exposed by the history and restore endpoints below). If the wrong photo gets uploaded, it's recoverable via:

```bash
curl -s -H "x-api-key: $LENIE_API_KEY" "http://192.168.200.7:5055/contacts/<id>/photo/history"
curl -s -H "x-api-key: $LENIE_API_KEY" -H "Content-Type: application/json" \
  -X POST "http://192.168.200.7:5055/contacts/<id>/photo/restore" -d '{"storage_key": "<key from history>"}'
```

...or the "Historia zdjęć" panel on the contact page in the web UI.

## Important

- All communication with the user in **Polish**.
- Never scrape or guess at a Facebook profile the user hasn't confirmed belongs to the contact — a wrong-person photo is worse than no photo.
- This skill only writes to the private contact book (`contacts`, `contact_photos`, `contact_links`, `contact_education`, `contact_interests`/`contact_interest_memberships`, `contact_lookup_results`) via the REST API — it never posts, messages, or interacts with anything on Facebook itself, only reads the public/logged-in-visible profile picture and "Informacje" tab.
- `current_city`/`hometown`/`gender` are plain columns on `Contact` (see `library/db/models.py`), visible to every auth kind (unlike `private_notes`, which is service-only) — they're meant to be seen at a glance, not hidden. `gender` is constrained to `male`/`female`/`other` by a DB check constraint (`ck_contacts_gender`) — anything else the profile shows (a custom/nonbinary label) maps to `other`, never invented as free text.
- Never overwrite an existing `gender`/`birthday` with a guess — if Facebook's value looks inconsistent with what's already recorded (e.g. contradicts a name-based assumption), flag it to the user instead of silently changing it.
- `contact_interests` is a **shared dictionary across the whole contact book** (like `contact_groups`) — creating a new tag affects every contact, not just this one. Always check for a case-insensitive name match before creating one, and keep names generic/reusable (`badminton`, not `badminton z Rafałem`).
- Hobby extraction (Step 5b) is intentionally conservative — when in doubt whether something is a genuine stated hobby versus a passing mention, skip it. A missing hobby tag costs nothing; a wrong one pollutes a shared dictionary other contacts' records will also show up under.
- Works one contact at a time; for a batch of contacts, run the workflow once per contact rather than trying to parallelize Chrome tabs against the same logged-in session.
