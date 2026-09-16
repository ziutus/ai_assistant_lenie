---
name: 'lenie-contact-facebook-photo'
description: 'Fetch a contact''s current Facebook profile picture and small-talk facts (current city, hometown) via the logged-in Claude in Chrome browser, and save them to Lenie''s private contact book'
---

Give a contact in Lenie's private contact book (`backend/library/contact_routes.py`) a profile photo pulled from their Facebook profile picture, plus two structured small-talk facts from the "Informacje" tab — `current_city` (mieszka w) and `hometown` (pochodzi z). Useful when a contact is known to have a Facebook profile but is missing this data in Lenie. The small-talk angle matters here: these two facts are deliberately kept as their own structured fields (not buried in free-text notes) so they're easy to scan before a conversation — see `[[user_accessibility_social_interaction]]` in memory for why the contact book treats this kind of thing as a first-class need, not a nice-to-have.

## Input

- A reference to the contact: a bare numeric contact ID, or a link like `http://192.168.200.7:3000/contacts/180`.
- Optionally, a Facebook profile URL (`https://www.facebook.com/<slug-or-id>`). If not given, look it up on the contact record first (see Step 1) before asking the user.

## Workflow

All contact-book calls go to the NAS backend REST API (`http://192.168.200.7:5055`) with header `x-api-key: $LENIE_API_KEY` (service key, see `[[reference_lenie_api_key]]` in memory).

### Step 1: Resolve the contact and the Facebook URL

```bash
curl -s -H "x-api-key: $LENIE_API_KEY" "http://192.168.200.7:5055/contacts/<ID>"
```

Note `uuid`, `display_name` (or `first_name`/`last_name`), existing `photo_url`, `current_city`, and `hometown`. Look at the `links` array for an entry with `link_type: "facebook"` — that's the profile URL to use.

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

### Step 5: Pull small-talk facts from the "Informacje" tab

While still on the profile, navigate to `<profile_url>/about_places` (or click **Informacje** → **Miejsca, w których mieszkał(a)**). Facebook shows up to two relevant rows there:

- **"Obecne miasto"** / "Mieszka w" → `current_city`
- **"Rodzinne miasto"** → `hometown`

Take a `screenshot` or use `get_page_text` to read the values — this is plain visible text, not blocked like the CDN image URLs in Step 3. Only take a value that is explicitly labeled; don't infer a city from an unrelated post or check-in.

Skip this step (and say so in the report) if the section is empty, hidden by the profile's privacy settings, or the profile has no separate "Informacje" tab visible while logged in as this account.

If either value is found and differs from what's already on the contact (from Step 1), save it:

```bash
curl -s -H "x-api-key: $LENIE_API_KEY" -H "Content-Type: application/json; charset=utf-8" \
  -X PATCH "http://192.168.200.7:5055/contacts/<ID>" \
  --data-binary '{"current_city": "<current city found>", "hometown": "<hometown found>", "change_source": "osint_lookup", "change_note": "Uzupełnione z zakładki Informacje na Facebooku"}'
```

Only include the keys you actually found (omit `current_city`/`hometown` entirely rather than sending an empty string, which would clear an existing value). Use a UTF-8 file with `--data-binary @file.json` instead of an inline `-d` string if either value contains Polish diacritics and you're building the JSON through shell interpolation (see the Polish-text gotcha in `[[project_contact_photo_split_skill]]`).

### Step 6: Verify and clean up

```bash
curl -s -H "x-api-key: $LENIE_API_KEY" "http://192.168.200.7:5055/contacts/<ID>" \
  | python3 -c "import json,sys; d=json.load(sys.stdin)['contact']; print(d['photo_url'], d['current_city'], d['hometown'])"
```

Confirm `photo_url` is non-null and different from before the upload, and `current_city`/`hometown` reflect what was found (or are unchanged if Step 5 found nothing new). Delete the temporary screenshot file(s) from the OS temp dir. Close the Chrome tab you opened (`tabs_close_mcp`) unless the user asked to keep it open.

### Step 7: Report

Tell the user, in Polish: which contact was updated, where the photo came from (profile URL, which album/photo), and which small-talk facts (if any) were added or already present. Give the test link `http://192.168.200.7:3000/contacts/<id>`.

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
- This skill only writes to the private contact book (`contacts`, `contact_photos`, `contact_links`) via the REST API — it never posts, messages, or interacts with anything on Facebook itself, only reads the public/logged-in-visible profile picture and "Informacje" tab.
- `current_city`/`hometown` are plain `String(200)` columns on `Contact` (see `library/db/models.py`), visible to every auth kind (unlike `private_notes`, which is service-only) — they're meant to be seen at a glance, not hidden.
- Works one contact at a time; for a batch of contacts, run the workflow once per contact rather than trying to parallelize Chrome tabs against the same logged-in session.
