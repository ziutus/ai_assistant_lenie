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

Read `contact.photo.id`, then fetch `GET /contact_photos/<uuid>` with the same auth.
Use this photo object's `photo_url`, `user_description`, classification and `contacts`.
If `subject_kind == no_people`, do not split. If the anchor's contact link has
`depicts_contact === false`, stop the automatic contact-and-family scenario.
If classification is `unknown`, you MUST view the image yourself; AI text is not evidence.
Always download and visually inspect the original before selecting crops. If only one
person is visible, report that there is nothing to split.

### Step 2: Identify people using user knowledge

Identify the anchor and other people only from explicit user knowledge, including the
photo's user description. Do not infer a spouse, parent, child or twins from appearance,
proximity, matching clothes or agreement between AI descriptions. If identity or the
requested creation scope is unclear, ask before creating contacts. Unnamed people may
use neutral display labels; family role labels require user-provided facts.

### Step 3: Crop

**First, get precise face positions instead of eyeballing them.** `backend/imports/detect_faces.py` (`library/face_detection.py`, OpenCV Haar cascade, optional dependency) prints every detected face as a pixel bounding box:

```bash
cd "C:\Users\ziutus\git\_lenie-all\lenie-server-2025\backend"
uv sync --extra imaging          # once per venv — installs opencv-python-headless
.venv/Scripts/python.exe imports/detect_faces.py "<path>\original.png"
```

Returns `{"count": N, "faces": [{"x", "y", "w", "h"}, ...]}`, sorted left to right. Match each returned face to a person from Step 2 by its `x`/`y` position (compare against what you saw in the photo). Verified in practice: reliably finds both faces in a two-adult photo; in a busier photo with children it can miss one (small/turned/blurred face) — that's fine, it's an aid for precision, not a hard requirement, and Step 2's "ask before creating child contacts" already handles the person a missed face would belong to.

**Derive crop boundaries from face centers**, one boundary per adjacent pair of *selected* faces (the ones you're actually splitting out — skip faces you're not creating a contact for, e.g. an unconfirmed bystander):
- face center = `x + w/2`
- boundary between two adjacent people = midpoint of their two centers
- leftmost person's crop starts at image `x=0`, rightmost person's crop ends at image `x=width`
- full image height for every crop (`y0=0, y1=height`) — matches the casual "cropped phone photo" look established in real sessions; don't try to tightly bound vertically around just the face

If `detect_faces.py` isn't usable (dependency not installed, or a face-detection edge case — profile view, obstruction) fall back to picking boundaries by eye from the downloaded image; a generous full-height rectangular crop around each person is enough, some overlap/background/other-person spillover at the edges is acceptable.

```bash
.venv/Scripts/python.exe -c "
from PIL import Image
img = Image.open(r'<path>\original.png')
w, h = img.size
crop_a = img.crop((x0, y0, x1, y1))
crop_a.save(r'<path>\person_a.png')
"
```

**Always view each crop with Read before uploading it** — if a crop looks bad (cuts off a face, wrong person centered), adjust the box and re-crop rather than uploading a bad result.

### Step 4: Upload the anchor's own crop

```bash
curl -s -H "x-api-key: $LENIE_API_KEY" \
  -F "photo=@<path>/person_a.png;filename=<name>.png;type=image/png" \
  "http://192.168.200.7:5055/contacts/<ID>/photo"
```

This mints a new immutable storage key — the previous (unsplit) photo is **not deleted**, see "Safety net" below.

### Step 5: Create a placeholder contact for each other adult

**Default to NOT asking for a real name.** Create the contact with a descriptive `display_label` and a `notes` field recording the user-provided facts — the name/relationship gets filled in later, by the user, once actually known. (Confirmed by the user across two real sessions: asked once whether to prompt for a name vs. leave blank, the answer was "leave blank, fill in later" — treat that as the standing default, not something to re-ask each time.)

Write the JSON body to a file first (see "Gotcha" below — do not inline-interpolate Polish text into `curl -d` from a shell loop):

```json
{
  "category_id": 1,
  "display_label": "Osoba ze zdjęcia <AnchorDisplayName>",
  "notes": "<Explicit user-provided facts; no visual relationship guesses>",
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

### Step 6: Add relationships from user knowledge

Create relationships only when explicitly supported by user knowledge. One row is
enough: `POST /contacts/<A>/relationships` with `related_contact_id: B`, the type
expressing who B is to A, and a note recording the user's source. The UI displays both
directions; do not create reciprocal duplicates. If the relationship is unknown,
leave it unset rather than persisting an appearance-based guess.

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
