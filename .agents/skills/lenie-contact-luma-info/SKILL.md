---
name: 'lenie-contact-luma-info'
description: 'Pull a contact''s public Luma (luma.com) profile - photo, short bio, LinkedIn and website links - and save it to Lenie''s private contact book'
---

Give a contact in Lenie's private contact book (`backend/library/contact_routes.py`) the data from their public Luma profile page (`https://luma.com/user/usr-...`): profile photo, short bio (`bio_short`, e.g. "Product developer"), and the social links the person entered (LinkedIn, website, X, Instagram, YouTube, TikTok). Useful for people met at events (e.g. contacts created from a WhatsApp community group) where Luma is often the only profile you have.

Unlike the Facebook/LinkedIn siblings ([lenie-contact-facebook-enrich](../lenie-contact-facebook-enrich/SKILL.md), [lenie-contact-linkedin-info](../lenie-contact-linkedin-info/SKILL.md)) this skill needs **no browser and no login**: the public page embeds the profile in its server-rendered `__NEXT_DATA__`, which `luma_profile.py` (next to this file) extracts. Luma shows only what the person typed in, so any field may be empty; there is no e-mail or phone.

## Input

- A reference to the contact: a bare numeric contact ID, or a link like `http://192.168.200.7:3000/contacts/664`.
- A Luma profile URL (`https://luma.com/user/usr-XXXX`, also `lu.ma`). If not given, look for a stored link on the contact (Step 1); if none, ask the user - never search Luma by name.

## Runtime and API configuration

Shared procedure for Claude Code and Codex. Use `LENIE_API_KEY` from the agent environment for the NAS API (`http://192.168.200.7:5055`, header `x-api-key`). Never print it or store it in this repository. Paths are relative to the repository root.

The curl examples are Bash examples. In PowerShell use `$env:LENIE_API_KEY`, `Invoke-RestMethod` with UTF-8 JSON bytes, and `curl.exe` (not the `curl` alias) for the multipart photo upload. Check HTTP errors before continuing; after an uncertain write, read the record back before retrying so links are not duplicated.

## Workflow

### Step 1: Resolve the contact and the Luma URL

```bash
curl -s -H "x-api-key: $LENIE_API_KEY" "http://192.168.200.7:5055/contacts/<ID>"
```

Note `display_name`, `notes`, `photo_url`, `company`, and the `links` array. Luma has no `link_type` of its own, so a Luma link is stored as `link_type: "other"` with a `label`-less `luma.com/user/...` URL - match existing links by that host.

### Step 2: Fetch the profile

```bash
python -I .agents/skills/lenie-contact-luma-info/luma_profile.py "<luma url>" --photo "<scratchpad>/luma_<ID>.jpg"
```

On Windows use the contact-venv-free system `python`; the script uses only the standard library. It prints JSON: `name`, `bio_short`, `avatar_url`, `website`, `linkedin_url`, `*_handle`, `timezone`, `luma_id`. A missing `__NEXT_DATA__` error means the URL is not a profile or Luma changed its layout - report it and stop.

Check the photo visually (Read tool) before uploading: Luma's default avatar is a generic silhouette/initials image. Do not upload a placeholder; record "zdjęcie: brak".

### Step 3: Identity check

Compare the Luma `name` with the contact's `display_name`. Luma's stored `first_name`/`last_name` can differ from the display name (seen: display "Marti Kuc", stored "Kama Mare") - ignore the stored pair. If the names do not plausibly match (a WhatsApp contact "Martyna" vs Luma "Marti Kuc" is a plausible match; two different first names is not), show both to the user and ask before saving anything. Do not rename the contact from Luma; propose the full name as a suggestion in the report.

### Step 4: Save

Only add what is missing; skip anything already stored.

1. **Photo** (if real and the contact has none; if one exists, ask before replacing - nothing is destroyed, photo history keeps old ones):
   ```bash
   curl -s -H "x-api-key: $LENIE_API_KEY" -X POST -F "photo=@<path>" "http://192.168.200.7:5055/contacts/<ID>/photo"
   ```
   Do not add a `;type=` suffix to the `-F` value (breaks curl in Git Bash).
2. **Links** - one `POST /contacts/<ID>/links` per value, matching existing links by URL (case-insensitive, ignoring a trailing slash):
   ```bash
   curl -s -H "x-api-key: $LENIE_API_KEY" -H "Content-Type: application/json; charset=utf-8" \
     -X POST "http://192.168.200.7:5055/contacts/<ID>/links" \
     --data-binary '{"link_type": "<linkedin|website|twitter|instagram|other>", "url": "<url>"}'
   ```
   Luma profile → `other`; `linkedin_url` → `linkedin`; `website` → `website`; X handle → `twitter` (`https://x.com/<handle>`); Instagram handle → `instagram` (`https://instagram.com/<handle>`). YouTube/TikTok handles → `other`.
3. **Bio** - append one line to `notes` (PATCH `/contacts/<ID>`, keep existing text, `change_source: "osint_lookup"`, `change_note: "Uzupełnione z profilu Luma"`): `Luma: <bio_short> (<luma url>)`. Skip if the bio is empty or already in the notes. Do not put the bio in `company` - it is a role description, not an employer.

Use `--data-binary @file.json` instead of an inline string when values have Polish diacritics (Git Bash mangling gotcha).

### Step 5: Verify and report

```bash
curl -s -H "x-api-key: $LENIE_API_KEY" "http://192.168.200.7:5055/contacts/<ID>"
```

Report in Polish: what was added (photo, each link, bio), what was already present or empty, any identity doubt, and the suggested full name. If a LinkedIn link was found, offer to run [lenie-contact-linkedin-info](../lenie-contact-linkedin-info/SKILL.md) on it (it needs the logged-in browser). Give the test link `http://192.168.200.7:3000/contacts/<ID>`.

## Important

- All communication with the user in **Polish**.
- Read-only on Luma: public page, no login, no follow/register actions. Fetch only `luma.com` / `lu.ma` profile URLs the user gave or the contact already stores.
- Writes go only to the private contact book via the REST API.
- Works one contact at a time.
