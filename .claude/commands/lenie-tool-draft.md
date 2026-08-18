# Tool Draft from Accepted Candidate

Generate a full "Narzędzie" (tool) description from an accepted tool candidate, following the existing Obsidian `appliaction description` template, then present it for review. Do NOT write any file or call any save endpoint — `POST /tools` doesn't exist yet (Epic 46/47, backlog), so this command always stops at presenting the draft.

## Input

Parse `$ARGUMENTS` as: `<CANDIDATE_ID> [optional comment — the user's own experience with the tool]`

Examples:
- `/lenie-tool-draft 5` — just the ID
- `/lenie-tool-draft 5 używam go do szybkich promptów w terminalu` — ID + personal note

If a comment is provided, treat it as a seed for the draft's `Additional Notes` section (analogous to the `personal_notes` field in the PRD's "Narzędzie" schema — the user's own experience, not a generic description restated from documentation).

## Workflow

Execute ALL steps below in order. Do NOT skip Step 6 (the stop condition) — this command never writes anything.

### Step 1: Fetch the candidate

```powershell
Invoke-RestMethod -Uri "http://192.168.200.7:5055/tool_candidates/<CANDIDATE_ID>" -Headers @{"x-api-key"=$env:LENIE_API_KEY}
```

Response is under the `tool_candidate` key (`id`, `name`, `status`, `context_snippet`, `detected_by`, `source_document_id`, `source_document: {id, title, url, byline, discovery_source, published_on, ingested_at}`).

**If `tool_candidate.status` is not `"accepted"`, STOP here** and tell the user:

> Kandydat #<CANDIDATE_ID> ma status `<status>`, nie `accepted` — draftowanie dostępne tylko dla zaakceptowanych kandydatów. Zaakceptuj go najpierw w widoku `/tool-candidates-review`.

Do not proceed to Step 2 or beyond when the guard triggers.

### Step 2: Fetch the source document's `uuid`

The candidate response already carries `title`/`url`/`byline`/`discovery_source`/`published_on`/`ingested_at` under `source_document` — but not `uuid`, and the project's source-line convention always uses `uuid`, never the numeric document id. Fetch it with one cheap metadata call (`include_text=0`, same pattern `/lenie-obsidian-note` Step 1a uses):

```powershell
Invoke-RestMethod -Uri "http://192.168.200.7:5055/website_get?id=<source_document_id>&include_text=0" -Headers @{"x-api-key"=$env:LENIE_API_KEY}
```

(`<source_document_id>` = `tool_candidate.source_document_id` from Step 1.) Use only `uuid` from this response — everything else needed is already in `tool_candidate.source_document`, don't re-fetch it.

### Step 3: Read the template

Read the template file at `$env:LENIE_OBSIDIAN_VAULT\templates\appliaction description.md` (the misspelling in the filename is real and pre-existing in the user's vault — do not "fix" it). If `$env:LENIE_OBSIDIAN_VAULT` is empty, the path doesn't exist, or the sandbox can't read it, STOP with a configuration instruction (same guard as `/lenie-obsidian-note`'s "Konfiguracja").

The template has: frontmatter `tags: [wiedza/informatyka]`, fields `Purpose`, `Type of application`, `Licence`, `homepage`, `wikipedia page`, `github page`, `Pricing type`, `pricing page`, sections `### Key Points`, `### Important Commands`, `### Additional Notes`, and a Templater-generated `## Source of note` footer that only works inside Obsidian itself — skip that footer section entirely in the draft (don't try to emulate Templater syntax).

Always read the template live in this step — never hardcode its contents in this command file, since the user may edit it later.

### Step 4: Fill missing fields via WebFetch/WebSearch

For `homepage`, `Licence`, `Pricing type`/`pricing page`, and optionally `wikipedia page`/`github page` — use WebFetch/WebSearch with `tool_candidate.name` and `tool_candidate.context_snippet` as search context. This is your own tool access — no new Lenie-side integration.

**Never invent a value.** If a field can't be confidently resolved, leave it as `TODO` in the draft rather than guessing — the user fills it in when editing.

### Step 5: Assemble the draft

Fill the template structure from Step 3 (don't invent a new format):

- `Purpose` — from `context_snippet` and/or what Step 4 found.
- `Type of application` — from the context found in Step 4.
- `Licence`, `homepage`, `wikipedia page`, `github page`, `Pricing type`, `pricing page` — from Step 4, or `TODO` where unresolved.
- `### Key Points` — 2-4 bullets from what was found.
- `### Important Commands` — empty code block if unknown (user fills in).
- `### Additional Notes` — the user's comment from `$ARGUMENTS` (Input section) if provided, otherwise empty.
- Frontmatter tags: keep exactly `tags: [wiedza/informatyka]` from the template. **Do not** add hierarchical `narzędzia/<slug>` tags — those are the `Tool` entity's `category_tags` (a database field, Epic 46), a separate mechanism from this markdown frontmatter tag; this command never creates a `Tool` row, so there is nothing to tag that way.
- Source line at the end (no chunk reference — this isn't chunk-based):
  `Źródło: [<source_document.title>](<source_document.url>) (Lenie AI uuid=<uuid from Step 2>, tool candidate id=<CANDIDATE_ID>)`

### Step 6: Present the draft — STOP (never write anything)

Show the full draft content in the chat as ready-to-copy markdown, together with:

1. An explicit list of fields that could not be auto-filled (marked `TODO` in the draft).
2. This exact statement: "Draft istnieje wyłącznie w tej sesji — `POST /tools` (zapis do bazy + wolumenu Obsidian z historią wersji) jeszcze nie istnieje (Epic 46/47, backlog). Nie zapisuję niczego do pliku ani do bazy."

**Do not write a file to the vault** (unlike `/lenie-obsidian-note`'s Step 9) and **do not call any save endpoint** — see "Important" below for why. This is the last step of this command.

## Important

- All notes and communication in **Polish**.
- Obsidian vault location: `$env:LENIE_OBSIDIAN_VAULT` — never hardcode the absolute vault path in this file or in any command output.
- Steps 1-2 read the database via the REST API on the NAS backend (`http://192.168.200.7:5055`), using `$env:LENIE_API_KEY` (a `kind=service` key — set once in the PowerShell profile, never hardcoded here).
- **Why this command never writes to the vault or the database:** for regular knowledge notes (`/lenie-obsidian-note`), Claude Code writing the file directly is fine — the backend never claims ownership of those files. Tool entities are different by design: `POST /tools` (once built, Epic 47) is the single point that atomically writes a `Tool` row plus an `obsidian_note_versions` entry *before* writing the file — a versioning guarantee this command must not bypass by writing the file itself. So this command always stops at Step 6, even though it technically has filesystem access.
- Always include the source with the document's **uuid** (not numeric id) — matches the project-wide convention used by `/lenie-obsidian-note`.
- **Never invent field values** — an unresolved field is `TODO`, not a guess.
