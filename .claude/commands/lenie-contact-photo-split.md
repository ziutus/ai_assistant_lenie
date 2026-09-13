---
name: 'lenie-contact-photo-split'
description: 'Split a contact photo showing several people into individual portraits: keep the anchor contact's own crop, create linked placeholder contacts for the other adults, and wire up relationships'
---

Turn a group/couple/family photo attached to one contact in Lenie's private contact book (`backend/library/contact_routes.py`) into separate per-person portraits, without losing the original photo (it stays recoverable via the photo-history feature — see "Safety net" below).

## Input

A reference to the **anchor contact** — the contact whose photo needs splitting: a bare numeric contact ID, or a link like `http://192.168.200.7:3000/contacts/494`.

## Workflow

All calls go to the NAS backend REST API (`http://192.168.200.7:5055`) with header `x-api-key: $LENIE_API_KEY` (service key, see `[[reference_lenie_api_key]]` in memory).

### Step 1: Fetch the contact and look at the photo

```bash
curl -s -H "x-api-key: $LENIE_API_KEY" "http://192.168.200.7:5055/contacts/<ID>"
```

Note `uuid`, `photo_url`, `groups`, `category_id`, `display_name`. Download the photo and actually look at it (Read tool on the downloaded file — this is a vision task, don't guess from the AI-generated `photo.ai_descriptions` text alone, though it's a useful hint for how many people/what they're wearing):

```bash
mkdir -p "$CLAUDE_JOB_DIR/tmp/contact<ID>"
curl -s -o "$CLAUDE_JOB_DIR/tmp/contact<ID>/original.png" "<photo_url from above>"
```

**If the photo shows only one person, stop here and tell the user — there's nothing to split.**

### Step 2: Identify the people

For each person in the photo, judge whether they are plausibly:
- **the anchor contact themself** (usually confirmable by comparing to context — the contact's name/notes/existing description),
- **a household-relevant adult** (spouse/partner) — a person prominent in the photo, standing directly with the anchor,
- **a child or an incidental bystander** — a minor, or someone only partially visible / clearly not part of the immediate household.

Only the first two categories get split into their own contact by default. For the third, **stop and ask the user** whether they want separate contacts created too — do not assume. (Rationale from real sessions: adults handled automatically without pushback; the first time children appeared in a photo, the right call was to mention them and wait rather than creating contacts unprompted.)

### Step 3: Crop

Use the backend venv's Pillow (already a dependency, `library/contact_photos.py` uses it):

```bash
cd "C:\Users\ziutus\git\_lenie-all\lenie-server-2025\backend" && .venv/Scripts/python.exe -c "
from PIL import Image
img = Image.open(r'<path>\original.png')
w, h = img.size
crop_a = img.crop((x0, y0, x1, y1))
crop_a.save(r'<path>\person_a.png')
"
```

Pick boundaries by eye from the downloaded image (there is no face-detection step in this skill — a generous full-height rectangular crop around each person is enough, some overlap/background/other-person spillover at the edges is acceptable, matching what a manually cropped phone photo looks like). **Always view each crop with Read before uploading it** — if a crop looks bad (cuts off a face, wrong person centered), adjust the box and re-crop rather than uploading a bad result.

### Step 4: Upload the anchor's own crop

```bash
curl -s -H "x-api-key: $LENIE_API_KEY" \
  -F "photo=@<path>/person_a.png;filename=<name>.png;type=image/png" \
  "http://192.168.200.7:5055/contacts/<ID>/photo"
```

This mints a new immutable storage key — the previous (unsplit) photo is **not deleted**, see "Safety net" below.

### Step 5: Create a placeholder contact for each other adult

**Default to NOT asking for a real name.** Create the contact with a descriptive `display_label` and a `notes` field flagging the guess as unconfirmed — the name/relationship gets filled in later, by the user, once actually known. (Confirmed by the user across two real sessions: asked once whether to prompt for a name vs. leave blank, the answer was "leave blank, fill in later" — treat that as the standing default, not something to re-ask each time.)

Write the JSON body to a file first (see "Gotcha" below — do not inline-interpolate Polish text into `curl -d` from a shell loop):

```json
{
  "category_id": 1,
  "display_label": "<Role> <AnchorDisplayName> (niepotwierdzone)",
  "notes": "Prawdopodobnie <role> kontaktu <AnchorDisplayName> (id <ID>) — rozpoznanie na podstawie wspólnego zdjęcia z grupy „<group name>”. Tożsamość NIE została potwierdzona, imię/nazwisko do uzupełnienia po weryfikacji.",
  "change_source": "manual_edit",
  "change_note": "Utworzono z podzielonego zdjęcia kontaktu <ID> (<AnchorDisplayName>)."
}
```

```bash
curl -s -H "x-api-key: $LENIE_API_KEY" -H "Content-Type: application/json; charset=utf-8" \
  -X POST "http://192.168.200.7:5055/contacts" --data-binary @new_contact.json
```

`<Role>` examples: "Żona"/"Mąż", "Syn"/"Córka" (only once the user has confirmed children should get their own contacts — Step 2). Use `category_id` matching the anchor's own category unless there's a reason not to (usually the same "Osoba prywatna").

Then:
- Upload that person's crop the same way as Step 4, to the new contact's id.
- Add them to every group the anchor belongs to (`POST /contacts/<new_id>/groups {"group_id": N}`), if that grouping is relevant to why the photo exists (e.g. a kindergarten-parents group).

### Step 6: Add relationships, both directions

Use a specific, gendered Polish term for each direction rather than a generic "member of family" label — matches the existing vocabulary already in `contact_relationships` (`żona`/`mąż`; extend as needed, e.g. `syn`/`córka` outgoing from parent, `matka`/`ojciec` incoming from child — there's no fixed enum, `relationship_type` is free text, see `ContactRelationship` in `backend/library/db/models.py`). Mark both rows as unconfirmed:

```bash
curl -s -H "x-api-key: $LENIE_API_KEY" -H "Content-Type: application/json; charset=utf-8" \
  -X POST "http://192.168.200.7:5055/contacts/<A>/relationships" --data-binary @- <<'EOF'
{"related_contact_id": <B>, "relationship_type": "<term from A's perspective>", "note": "Niepotwierdzone — rozpoznanie na podstawie wspólnego zdjęcia, do weryfikacji."}
EOF
```

Repeat with `<A>`/`<B>` swapped and the reciprocal term. If a family has more than two members split out (e.g. two parents + a child), link the child to **both** parents, not just the anchor — a real family graph, not just a star around the anchor contact.

### Step 7: Report

Tell the user, in Polish: what was split, which new contact id(s) were created, which relationships were added, and give a test URL (`http://192.168.200.7:3000/contacts/<id>` for each contact touched). Mention explicitly that the original combined photo is not lost.

## Safety net: photo history

Every photo upload mints a new immutable storage key (`_photo_storage_key()` in `contact_routes.py`) and never deletes the previous `ContactPhoto` row or file — so a bad crop is always recoverable. This is exposed via (added specifically to make this kind of photo edit safe, PR #660):

```bash
curl -s -H "x-api-key: $LENIE_API_KEY" "http://192.168.200.7:5055/contacts/<id>/photo/history"
curl -s -H "x-api-key: $LENIE_API_KEY" -H "Content-Type: application/json" \
  -X POST "http://192.168.200.7:5055/contacts/<id>/photo/restore" -d '{"storage_key": "<key from history>"}'
```

...and as a "Historia zdjęć" panel on the contact page in the web UI. If a crop turns out wrong after the fact, restore first, then re-crop and re-upload — never worry that a mistake here is unrecoverable.

## Gotcha: JSON request bodies with Polish text

`curl -d "...$shellvar..."` built inside a `for`/`cut`-based shell loop can silently corrupt the JSON (stray characters mangle it, `get_json(silent=True)` then returns `{}`, and every field looks "missing" even though the contact IDs were real) — this actually happened in a real session and produced a confusing wall of "related_contact_id not found" errors for otherwise-valid requests. Always send the body either as a heredoc (`--data-binary @- <<'EOF' ... EOF`, single-quoted delimiter so `$`/backticks aren't expanded) or as a UTF-8 file written with the `Write` tool (`--data-binary @file.json`) — never build it through nested shell substitution in a loop.

## Important

- All communication with the user in **Polish**.
- Never invent a real name for a person you can't actually identify — leave `first_name`/`last_name` empty, use `display_label` + `notes` instead (see Step 5).
- This skill only writes to the private contact book (`contacts`, `contact_photos`, `contact_relationships`, `contact_group_memberships`) via the REST API — it never touches the document library or the Obsidian vault.
- If the "photo history" endpoints (`/contacts/<id>/photo/history`, `/photo/restore`) 404, the feature hasn't been deployed to the NAS yet — check `docker ps` there and redeploy backend/frontend before relying on it as a safety net.
