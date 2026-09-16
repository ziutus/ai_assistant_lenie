---
name: 'lenie-contact-facebook-enrich'
description: 'Fetch a contact''s current Facebook profile picture and structured facts (current city, hometown, gender, birthday, education, hobby/interest tags) via the logged-in Claude in Chrome browser, and save them to Lenie''s private contact book'
---

Give a contact in Lenie's private contact book (`backend/library/contact_routes.py`) a profile photo pulled from their Facebook profile picture, plus structured facts from the "Informacje" tab: `current_city` (mieszka w), `hometown` (pochodzi z), `gender`, `birthday`/`birthday_month`/`birthday_day`, education entries (`contact_education`), and hobby/interest tags (`contact_interests`). Useful when a contact is known to have a Facebook profile but is missing this data in Lenie.

Several different motivations drive this, worth keeping straight when deciding what to pull:
- `current_city`/`hometown` are **small-talk aids** — concrete, low-effort conversation topics, kept as their own structured fields (not buried in free-text notes) so they're easy to scan before a conversation. See `[[user_accessibility_social_interaction]]` in memory for why the contact book treats this as a first-class need, not a nice-to-have.
- `gender` is a **disambiguation aid**, not a small-talk topic — most useful for foreign names/surnames where gender isn't obvious from the name alone and no photo exists yet (real incident that prompted this: a Korean contact's gender was wrongly assumed from the name alone).
- `birthday` is already a first-class field (backs the "Nadchodzące urodziny" view) — this skill is just another way to fill it in when it's visible on Facebook but missing in Lenie.
- Education (`contact_education`, one row per school/university) and hobby tags (`contact_interests`, a shared dictionary M:N with contacts — same pattern as `contact_groups`) are both **small-talk aids** like city/hometown, but structured so they're searchable/filterable across contacts (e.g. "who plays badminton?"), not buried in free-text `notes`.

## Input

- A reference to the contact: a bare numeric contact ID, or a link like `http://192.168.200.7:3000/contacts/180`.
- Optionally, a Facebook profile URL (`https://www.facebook.com/<slug-or-id>`). If not given, look it up on the contact record first (see Step 1) before asking the user.

## Workflow

All contact-book calls go to the NAS backend REST API (`http://192.168.200.7:5055`) with header `x-api-key: $LENIE_API_KEY` (service key, see `[[reference_lenie_api_key]]` in memory).

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
- If the contact already has a `photo_url`, mention that a photo already exists and confirm the user wants to replace it before continuing (it isn't destructive — see "Safety net" below — but worth a heads-up).

### Step 2: Open the profile in Chrome and find the current profile picture

Load the Chrome tools in one `ToolSearch` call if not already loaded: `select:mcp__claude-in-chrome__tabs_context_mcp,mcp__claude-in-chrome__navigate,mcp__claude-in-chrome__computer,mcp__claude-in-chrome__find,mcp__claude-in-chrome__get_page_text,mcp__claude-in-chrome__tabs_close_mcp`. The user must already be logged into Facebook in that Chrome profile — this skill doesn't handle login.

1. `tabs_context_mcp` (createIfEmpty: true), then `navigate` to the profile URL.
2. **Do not click the small circular avatar directly** — on a profile with family members linked, that hot zone often opens a "Członkowie rodziny" (family members) popup instead of the photo. The reliable path is via the album:
   - Click the **Zdjęcia** tab.
   - Click the **Albumy** sub-tab.
   - Click the **"Zdjęcia profilowe"** album thumbnail.
   - Click the first (most recent / currently-active) photo in that album to open the full-size photo lightbox.
3. Take a `screenshot` to see the lightbox layout and confirm the photo shown is a real, current profile picture (check the caption/date if visible) and that it's actually of the expected person, not a placeholder or a group photo.

If the "Zdjęcia profilowe" album is empty, private, or doesn't exist (privacy settings vary per profile), fall back to a `zoom` capture of the small circular avatar on the main profile page instead — lower resolution, but better than nothing. Tell the user the source was lower-quality when reporting back.

### Step 3: Capture the photo as a local file

**Do not try to read the image URL via `javascript_tool`** — Facebook's CDN URLs carry signed query-string tokens, and the Chrome extension deliberately blocks reading any URL containing cookie/query-string data (returns `"[BLOCKED: Cookie/query string data]"`). There is no way around this and no need to fight it.

Instead, capture pixels directly:

```
computer(action: "zoom", tabId: <id>, region: [x0, y0, x1, y1], save_to_disk: true)
```

Pick `region` to tightly bound the photo pane in the lightbox (use the preceding screenshot to read off pixel coordinates — the photo pane is the large dark-bordered area, not the comments sidebar). The tool response includes the saved file path under the OS temp dir.

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

Take a `screenshot` or use `get_page_text` to read the values on each page — this is plain visible text, not blocked like the CDN image URLs in Step 3. Only take a value that is explicitly labeled; don't infer a city, gender, birthday, or school from an unrelated post, check-in, or profile picture caption.

Skip whichever sub-section is empty or hidden by the profile's privacy settings (say so in the report), and skip the whole step if the profile has no "Informacje" tab visible while logged in as this account.

If any value is found and differs from what's already on the contact (from Step 1), save it in one PATCH call:

```bash
curl -s -H "x-api-key: $LENIE_API_KEY" -H "Content-Type: application/json; charset=utf-8" \
  -X PATCH "http://192.168.200.7:5055/contacts/<ID>" \
  --data-binary '{"current_city": "<current city found>", "hometown": "<hometown found>", "gender": "<male|female|other>", "birthday_month": <1-12>, "birthday_day": <1-31>, "change_source": "osint_lookup", "change_note": "Uzupełnione z zakładki Informacje na Facebooku"}'
```

Only include the keys you actually found (omit the rest entirely rather than sending an empty string/null, which would clear an existing value). `birthday_month`/`birthday_day` must be sent together — see `_validate_birthday_pair()` in `contact_routes.py`. Use a UTF-8 file with `--data-binary @file.json` instead of an inline `-d` string if any value contains Polish diacritics and you're building the JSON through shell interpolation (confirmed gotcha: inline `-d '...Łódź...'` in Git Bash on Windows silently mangles diacritics to ASCII — see the same warning in `[[project_contact_smalltalk_fields]]`).

For each education entry found that isn't already in the list fetched in Step 1 (match by `institution` name, case-insensitive), add it separately:

```bash
curl -s -H "x-api-key: $LENIE_API_KEY" -H "Content-Type: application/json; charset=utf-8" \
  -X POST "http://192.168.200.7:5055/contacts/<ID>/education" \
  --data-binary '{"institution": "<school/university name>", "field_of_study": "<if shown, else omit>"}'
```

### Step 5b: Hobby/interest tags (conservative — from self-described text only)

Facebook has no clean, explicitly-labeled "hobby" field. Do **not** derive hobby tags from the "Lubię to" / liked-Pages list — that's noisy (brands, media outlets, meme pages), not a curated statement of the person's own interests, and would pollute the shared `contact_interests` dictionary with junk that other contacts then have to wade through.

Instead, only take hobby tags from **prose the person wrote about themselves**: the profile's own bio/intro text on the main page (visible in the Step 2 screenshot, under the name — the same kind of self-authored blurb we already read as a LinkedIn headline in the sibling `lenie-contact-linkedin-info` skill), or an explicit "Zainteresowania"/custom-field entry if the profile has one. Extract only concrete, unambiguous nouns the person names as something they do (e.g. "biegam, gram w badmintona" → `bieganie`, `badminton`) — never a vague adjective or a business/brand mention from that same bio.

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

### Step 6: Verify and clean up

```bash
curl -s -H "x-api-key: $LENIE_API_KEY" "http://192.168.200.7:5055/contacts/<ID>" \
  | python3 -c "import json,sys; d=json.load(sys.stdin)['contact']; print(d['photo_url'], d['current_city'], d['hometown'], d['gender'], d['birthday'], d['birthday_month'], d['birthday_day'], d['interests'])"
curl -s -H "x-api-key: $LENIE_API_KEY" "http://192.168.200.7:5055/contacts/<ID>/education"
```

Confirm `photo_url` is non-null and different from before the upload, and the other fields (including `interests` and the education list) reflect what was found (or are unchanged if Step 5/5b found nothing new). Delete the temporary screenshot file(s) from the OS temp dir. Close the Chrome tab you opened (`tabs_close_mcp`) unless the user asked to keep it open.

### Step 7: Report

Tell the user, in Polish: which contact was updated, where the photo came from (profile URL, which album/photo), and which structured facts (if any) were added or already present — including education entries and hobby tags, or a note that Step 5b found nothing usable. Give the test link `http://192.168.200.7:3000/contacts/<id>`.

## Safety net: photo history

Uploading never deletes a previous photo — every upload mints a new immutable storage key (see `[[project_contact_photo_history_feature]]` in memory). If the wrong photo gets uploaded, it's recoverable via:

```bash
curl -s -H "x-api-key: $LENIE_API_KEY" "http://192.168.200.7:5055/contacts/<id>/photo/history"
curl -s -H "x-api-key: $LENIE_API_KEY" -H "Content-Type: application/json" \
  -X POST "http://192.168.200.7:5055/contacts/<id>/photo/restore" -d '{"storage_key": "<key from history>"}'
```

...or the "Historia zdjęć" panel on the contact page in the web UI.

## Important

- All communication with the user in **Polish**.
- Never scrape or guess at a Facebook profile the user hasn't confirmed belongs to the contact — a wrong-person photo is worse than no photo.
- This skill only writes to the private contact book (`contacts`, `contact_photos`, `contact_links`, `contact_education`, `contact_interests`/`contact_interest_memberships`) via the REST API — it never posts, messages, or interacts with anything on Facebook itself, only reads the public/logged-in-visible profile picture and "Informacje" tab.
- `current_city`/`hometown`/`gender` are plain columns on `Contact` (see `library/db/models.py`), visible to every auth kind (unlike `private_notes`, which is service-only) — they're meant to be seen at a glance, not hidden. `gender` is constrained to `male`/`female`/`other` by a DB check constraint (`ck_contacts_gender`) — anything else the profile shows (a custom/nonbinary label) maps to `other`, never invented as free text.
- Never overwrite an existing `gender`/`birthday` with a guess — if Facebook's value looks inconsistent with what's already recorded (e.g. contradicts a name-based assumption), flag it to the user instead of silently changing it.
- `contact_interests` is a **shared dictionary across the whole contact book** (like `contact_groups`) — creating a new tag affects every contact, not just this one. Always check for a case-insensitive name match before creating one, and keep names generic/reusable (`badminton`, not `badminton z Rafałem`).
- Hobby extraction (Step 5b) is intentionally conservative — when in doubt whether something is a genuine stated hobby versus a passing mention, skip it. A missing hobby tag costs nothing; a wrong one pollutes a shared dictionary other contacts' records will also show up under.
- Works one contact at a time; for a batch of contacts, run the workflow once per contact rather than trying to parallelize Chrome tabs against the same logged-in session.
