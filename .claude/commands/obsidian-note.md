# Obsidian Note from Article

Create or update Obsidian notes based on a Lenie DB article, then update the database.

## Input

Parse `$ARGUMENTS` as: `<ARTICLE_ID> [optional comment about why this article is interesting]`

Examples:
- `/obsidian-note 8812` — just the ID
- `/obsidian-note 8812 ciekawy wniosek o tym że "oś autokratów" to nie spójny sojusz` — ID + comment
- `/obsidian-note 8802 reżim nie może skapitulować, bo utrata twarzy = koniec władzy` — ID + key insight

If a comment is provided, treat it as **the user's key takeaway** — this is what matters most to them. Use it to:
1. Focus the note on that specific insight (don't just summarize the whole article)
2. Decide where to place the note (which existing note to update)
3. Skip the "discuss with user" step if the comment is clear enough — go straight to creating/updating notes

**`note` field from database (Chrome extension):** After fetching the article (Step 1), check if the `note` field is non-empty. If present, treat it exactly like a comment argument above — it is the user's thought recorded at save time. If both a CLI comment and a `note` field are present, combine both as the user's intent.

## Workflow

Execute ALL steps below in order. Do NOT skip step 6 (database update).

### Step 1: Fetch article metadata

All calls below go to the backend REST API on the NAS (`http://192.168.200.7:5055`) with the service API key from `$env:LENIE_API_KEY` (see "Important" at the bottom — set once in your PowerShell profile, never in this file). `Invoke-RestMethod` parses the JSON response into a PowerShell object automatically — no manual `ConvertFrom-Json` needed.

**Step 1a — metadata only (no text field, cheap):**

```powershell
Invoke-RestMethod -Uri "http://192.168.200.7:5055/website_get?id=<ARTICLE_ID>&include_text=0" -Headers @{"x-api-key"=$env:LENIE_API_KEY}
```

Returns the document's metadata fields (`id`, `uuid`, `title`, `url`, `ingested_at`, `processing_status`, `document_type`, `language`, `source`, `byline`, `note`, `summary`, `reviewed_at`, `tags`, `obsidian_note_paths`, `chapter_list`, `video_description`, `text_length`, plus other editor-only fields you can ignore) — `text`/`text_raw`/`text_md` are omitted by `include_text=0`. `text_length` reflects the same `text`-or-`text_raw` fallback as Step 1c, so it's non-zero even for raw, not-yet-cleaned documents.

Display the metadata to the user.

**Step 1b — Check for chunk analysis runs (all document types)**

Every document type can have chunk analysis runs — mode `transcript` (youtube/movie STT with rewrite) or mode `article` (webpage/link/text/book chapters, no rewrite). Always run this check, regardless of `document_type`.

A document can have **more than one run** (a book typically has one `split_only` run over the whole text plus one `article` run per chapter). List all runs first:

```powershell
Invoke-RestMethod -Uri "http://192.168.200.7:5055/analysis_runs?doc_id=<ARTICLE_ID>" -Headers @{"x-api-key"=$env:LENIE_API_KEY}
```

Returns JSON: `{"doc_id", "runs": [{"id", "mode", "status", "scope", "model", "created_at", "chunk_count", "temat_count", "analyzed_count", "approved_count", "workflow_stage"}, ...]}`. Note the run's own identifier is `id` here (not `run_id`) — that's the `<RUN_ID>` used in every call below.

**Interpret the result:**
- Empty `runs` array → proceed to **Step 1c** (fetch full text)
- **One run** → auto-select its `id` as `<RUN_ID>`, proceed straight to **Step 2a**
- **Multiple runs** → this is typically a book (chapter runs) or a document re-analyzed several times. Show the list to the user (id, mode, scope, temat/analyzed/approved counts). A run with `analyzed_count=0` is a `split_only` run — chunks exist but have no topic/summary yet, not usable for note-writing on its own (even if `approved_count` is non-zero — that can happen for stale/aborted runs where chunks were approved before topics were ever generated). Propose the run with the highest `analyzed_count` as the default (break ties by `approved_count`), but let the user pick a different `RUN_ID` (e.g. a specific chapter). Once a `RUN_ID` is chosen, proceed to **Step 2a**.

**Fetch chunks + topic sections for the chosen run** (used by Step 2a — also re-run this after the user picks a different `RUN_ID` from the multi-run list above):

```powershell
Invoke-RestMethod -Uri "http://192.168.200.7:5055/analysis_run/<RUN_ID>/chunks?lite=1" -Headers @{"x-api-key"=$env:LENIE_API_KEY}
```

Returns JSON with (among other editor-only fields you can ignore) `run` (`id`, `mode`, `status`, `scope`, `model`, `created_at`, `workflow_stage`), `chunk_total`, `chunks: [{"position", "type", "status", "topic", "summary", "obsidian_note_paths"}, ...]`, `topic_sections: [{"id", "position", "title", "chunk_positions", "temat_count", "approved_count", "notes_count"}, ...]`. Two differences from the old CLI output to apply yourself:
- **`chunks` is NOT pre-filtered to `TEMAT`** — it includes every chunk type. Filter to `type == "TEMAT"` yourself; the rest (`ZRODLA`/`REKLAMA`/`SZUM`) is `chunk_total` minus your filtered count (equivalent to the old `reklama_szum_count`).
- **No `done_count` per section** — derive it yourself from the (TEMAT-filtered) `chunks` array: for a section, `done_count` = count of chunks whose `position` is in that section's `chunk_positions` AND (`obsidian_note_paths` is non-empty OR `status == "skipped"`). This is the exact same predicate as the "Już w notatkach / pominięte" split used below — compute it once, reuse for both.

This single call backs both the flat chunk list and the section-grouped view in Step 2a — no separate section query needed.

If `mode=article`, chunk text (fetched later in Step 2a) has `corrected_text=None` for every chunk — that is normal for this mode (no rewrite step), not a data quality issue. See the note in Step 2a's "Content usage rules".

**Step 1c — Fetch full text (only when no chunks exist):**

Check `document_type` from Step 1a to decide the rule:

**For `youtube` or `movie`:**
- Transcription is stored in `text` in the DB regardless of state — the call below always returns it.
- If `text_length` from Step 1a is 0 → warn: "Brak transkrypcji dla tego dokumentu YouTube. Nie można utworzyć notatki."
- Otherwise → proceed directly to the full fetch.

**For `webpage`, `link`, or other types:**
- If `processing_status` is `URL_ADDED` or `DOCUMENT_INTO_DATABASE` → **STOP and warn the user**:
  > "Artykuł ma status `{state}` — tekst jest surowy (zawiera szum nawigacyjny strony, reklamy itp.) i zużyje znacznie więcej tokenów niż czysty artykuł. Pobierać mimo to?"
  Proceed only if user confirms.
- If `processing_status` is `DOCUMENT_CLEANED` or any later state → proceed to the full fetch.

```powershell
Invoke-RestMethod -Uri "http://192.168.200.7:5055/website_get?id=<ARTICLE_ID>" -Headers @{"x-api-key"=$env:LENIE_API_KEY}
```

(`include_text` omitted — defaults to `1`, so `text`/`text_raw`/`text_md` are included alongside everything from Step 1a.) Use `text` as the article content; if it's empty (raw, not-yet-cleaned states), fall back to `text_raw` — same fallback `text_length` already applied for you in Step 1a.

### Step 2a: Chunk-based flow (document has existing analysis chunks)

**Use this step whenever Step 1b found a run to use** (any document type — youtube/movie transcript chunks or webpage/link/text/book article chunks). This is the primary path whenever pre-reviewed chunks exist — it skips sending the full text to the LLM.

**If your TEMAT-filtered chunk count from Step 1b is large (> 30 — same threshold as the `/chunks/:id` UI's `SECTION_VIEW_THRESHOLD`), use the section-grouped view below instead of the flat list.** Typical case: books with a run per chapter, or a `split_only` whole-book run. Otherwise skip straight to **"Flat chunk list"**.

#### Section-grouped view (large runs — books)

No extra query needed — the `topic_sections` array from Step 1b's call already has `chunk_positions` (which positions belong to each section) and `temat_count`; `done_count` you compute yourself per Step 1b's note above. Chunks whose position doesn't appear in any section's `chunk_positions` are "uncovered" — topic sections don't always cover every `TEMAT` chunk (LLM synthesis is partial); group these under a synthetic "(chunki bez przypisanej sekcji)" entry.

**Display split into two groups (same top/bottom convention as the flat list):**
- **Sekcje ukończone** (`done_count == temat_count`) at the TOP, compact one-liners: `Rozdział N: Tytuł — ✓ wszystkie opracowane (n tematów)`
- **Sekcje do opracowania** (`done_count < temat_count`) at the BOTTOM: `Rozdział N: Tytuł — X/Y opracowanych`

**Ask the user** which section(s) to drill into (by `section_id`, or title). Then filter the `chunks` array already fetched in Step 1b to `position in section.chunk_positions` (for the uncovered group, `position` not in any section's `chunk_positions`) — no new DB call.

Display these per-section chunks using the same **Już w notatkach / Nieopracowane** split as the flat list below, then continue with "For each selected chunk — fetch full text".

#### Flat chunk list (normal-sized runs)

**Display the chunk list to the user** split into two groups, in this order (Już w notatkach FIRST, Nieopracowane LAST — chat auto-scrolls to bottom so user sees pending items immediately):

**Już w notatkach / pominięte** (non-empty `obsidian_note_paths` OR status == `skipped`) — show compactly, one line each:
- `#N [approved] Topic → Chiny.md, USA.md`
- `#N [skipped] Topic — pominięty`

**Nieopracowane** (empty `obsidian_note_paths` AND status != `skipped`) — these need work:
- position number, status badge (approved/pending/needs_reanalysis), topic, summary

Count of REKLAMA/SZUM chunks (filtered out automatically — SZUM is extraction junk like portal navigation).
Warning if any TEMAT chunks have status `needs_reanalysis` or `pending` (analysis incomplete) — this is unrelated to `corrected_text` being empty (see mode=article note below).

**Default proposal:** suggest working on unprocessed chunks only. If the user says "wszystkie" or "lista", show all.

Example display:
```
Run #42 — Bielik-11B-v3.0-Instruct (2026-06-30) — 8 tematów, 3 reklamy

=== Już w notatkach (4) ===
#1 [approved] Wprowadzenie gości → Chiny.md
#2 [skipped] Reklama XTB — pominięty
...

=== Nieopracowane (4) ===
#3 [approved] Sytuacja gospodarcza w regionie
   Rozmówcy analizują wpływ embarg na eksport ropy...
#6 [pending] Polityka celna USA
   ...
```

**Ask the user:** "Które nieopracowane tematy (numery) chcesz opisać? (podaj numery, lub 'wszystkie' dla wszystkich nieopracowanych)"

**For each selected chunk — fetch full text (works for both modes):**

```powershell
Invoke-RestMethod -Uri "http://192.168.200.7:5055/analysis_run/<RUN_ID>/chunks?positions=<comma_separated_positions>" -Headers @{"x-api-key"=$env:LENIE_API_KEY}
```

(No `lite` — full text for just the requested positions, without pulling the whole run.) Each item in `chunks` has `position`, `topic`, `status`, `original_text`, `corrected_text`. Unlike the old CLI's `--chunk-text`, the mode-aware fallback (below) is no longer pre-applied — pick the field yourself.

**Content usage rules:**
- If chunk has `summary` and `approved` status → use `summary` as the basis, enrich only if needed
- If chunk needs detail → pick the text field based on the run's `mode` (from Step 1b):
  - **mode=transcript** (youtube/movie) → use `corrected_text` (cleaned STT transcript with fillers/rewrite applied) — never the raw `original_text`.
  - **mode=article** (webpage/link/text/book) → use `original_text` — `corrected_text` is **always `None` by design** for this mode (no rewrite step, source markdown is already clean). This is expected behavior, not missing data, and should NOT be flagged as a data quality issue to the user.
- If chunk is `pending`/`needs_reanalysis` → warn user and ask if they want to proceed anyway (this is a status-based check, orthogonal to which text field is populated)

**Then proceed to Step 3** (find related notes).

### Step 2b: Standard content flow (no existing chunks)

**Use this step when:** the document has no chunk analysis runs at all (Step 1b's `/analysis_runs` call returned an empty `runs` array) — regardless of document type. Since Step 1b now checks every type, this step mainly applies to documents that were never run through `/analyze_chunks` yet.

Check `document_type` (Step 1a) and `text_length` (Step 1c):

#### Long YouTube video without chunks (document_type == "youtube" AND text_length > 10 000)

This is a long video transcript — treat it as a multi-topic document, NOT a single article.

1. Read the full text and identify **thematic sections** (typically 4-8 topics)
2. Present the user with a numbered list of sections
3. Ask: "Od której części zaczynamy?" or "Omawiamy po kolei?"
4. Process **one section at a time** — for each section:
   - Summarize key points (3-5 bullets)
   - Ask about financial angle: kto finansuje / skąd pieniądze / skala rynku
   - Propose: new note or update existing?
   - Show full note proposal, wait for approval
   - Save note, update index, update DB (append path)
5. Repeat for each section the user wants to cover
6. Each section may produce **one or more notes** — track all paths for DB update

**Do NOT** try to process the whole video at once into a single note.

#### Short article or webpage (text_length ≤ 10 000 OR document_type != "youtube")

Follow the standard single-note flow (Steps 3–6 below).

### Step 3: Find related notes via index

**Always start by reading the index:**

```
C:\Users\ziutus\Obsydian\personal\02-wiedza\_index.md
```

The index maps topics/keywords → file paths. Steps:
1. Read `_index.md`
2. Match keywords from the article title and main theme against the index entries
3. For country-specific articles: derive the path from the pattern `Geopolityka i polityka/Kraje/<Region>/<Kraj>.md` (regions: Afryka, Ameryka Południowa, Ameryka Północna, Azja, Bliski Wschód, Europa, Półwysep Arabski i Arabowie)
4. Open only the 1-2 most relevant files found in the index — read them to check existing content
5. **Use Grep/Glob only as fallback** if the topic is clearly not covered by the index

Report which notes were found and what they already contain.

### Step 4: Check geopolitical control questions (if applicable)

Check the `tags` field from the metadata (Step 1a output). If `tags` is empty, skip this step entirely.

Otherwise, fetch the already-selected control-question answers for this document — a cheap-LLM router (`library/control_question_selection.py`) has already narrowed the tag-matched question bank down to the ones this specific document actually answers, so unlike the old flow there's no separate "check which are answered" pass to do yourself:

```powershell
Invoke-RestMethod -Uri "http://192.168.200.7:5055/document/<ARTICLE_ID>/control_questions" -Headers @{"x-api-key"=$env:LENIE_API_KEY}
```

Returns JSON: `{"doc_id", "control_questions": [{"chapter_position", "question_id", "question_header", "tags", "answer_summary", "evidence"}, ...]}`.

**If `control_questions` is non-empty:** include those answers explicitly in the notes (as dedicated `##` sections matching the question topic, e.g. `## Aspiracje i cele strategiczne`, `## Konflikty`, `## Stan finansów`) using `answer_summary`/`evidence`.

**If `control_questions` is empty:** this document may simply not touch any control question, or it may just never have been run through the router yet (e.g. added outside the automatic enrichment pipeline). Trigger it on demand via REST — cheap, and a no-op if the tags genuinely don't match any question:

```powershell
Invoke-RestMethod -Uri "http://192.168.200.7:5055/document/<ARTICLE_ID>/select_control_questions" -Method Post -Headers @{"x-api-key"=$env:LENIE_API_KEY}
```

Then re-run the `GET /document/<ARTICLE_ID>/control_questions` call above. If it's still empty, the document genuinely doesn't answer any of the tag-matched questions — move on without this section.

### Step 4b: Check fragments marked for LLM discussion

Fetch the reader's fragment notes for this document, using the **user** API key
(`$env:LENIE_API_KEY_USER` — a `kind=user` key, distinct from the `kind=service`
`$env:LENIE_API_KEY` used everywhere else in this skill; this endpoint 403s for service keys):

```powershell
Invoke-RestMethod -Uri "http://192.168.200.7:5055/document/<ARTICLE_ID>/notes" -Headers @{"x-api-key"=$env:LENIE_API_KEY_USER}
```

Filter the returned `notes` array to those whose `tags` include `"llm-discuss"` — these are fragments the user explicitly flagged in the reader as "discuss this with the LLM" (via the 💬 button in the selection popover, `web_interface_react/src/modules/shared/components/ReaderNotes/readerNotes.tsx`). Each has `anchor_quote` (the exact fragment), `note_text` (optional free-text the user added), `tags`, `stance`, and `chapter_position`.

**If any such fragments exist:** treat them as an explicit signal of user intent, same weight as a CLI comment or the `note` field (see "Input" section above) — quote them back to the user in Step 5's discussion and make sure the note addresses each one, not just a general summary.

**If none exist:** skip silently, no need to mention it.

### Step 5: Discuss with user and create/update notes

Present the user with:
- Summary of the article (3-5 key points in Polish) — derived from chunk summaries if available
- Found related Obsidian notes
- Which control questions are answered (if geopolitics article)
- Proposal: create new note, update existing, or both

**Financial angle (always check):** For every note about technology, geopolitics, projects or companies — explicitly ask or include: kto finansuje, ile to kosztuje, skąd pochodzi zwrot z inwestycji, jaka jest skala rynku. If data is missing — mark as `TODO: wątek finansowy`. Bez pieniędzy nie ma efektów.

Wait for user input on what to create/update. Then create/update the Obsidian .md files following vault conventions:
- Frontmatter with tags (`tags: wiedza/...`)
- H1 heading
- Content with `##` sections, `**bold**` for key points
- Obsidian wiki-links `[[Country]]` for cross-references
- Source line at the end: `Źródło: [Title](URL) (Lenie AI uuid=UUID)` — use the `uuid` field from Step 1a's metadata (NOT the numeric `id`)

**For chunk-based notes (Step 2a):** Add a reference to the chunk topic at the end of the source line if it covers a specific chunk, e.g.: `Źródło: [Title](URL) (Lenie AI uuid=UUID, chunk #3 — "Sytuacja gospodarcza")`

**After creating/updating the note — update `_index.md` if needed:**
- If the note is a **new file** OR its topic has **no matching entry** in `_index.md` → add a line to the appropriate section in `_index.md` (keywords → path)
- If the note already exists in the index → skip
- `_index.md` is already in context from Step 3, so no extra read needed

### Step 6: Update database (MANDATORY — never skip)

After creating/updating Obsidian notes, ALWAYS update the database. Two objects need updating:

**A) `Document` — always update:**

```powershell
cd C:\Users\ziutus\git\_lenie-all\lenie-server-2025\backend; .venv/Scripts/python -c @"
from datetime import datetime
from library.db.engine import get_session
from library.db.models import Document
session = get_session()
doc = Document.get_by_id(session, <ARTICLE_ID>)
paths = list(doc.obsidian_note_paths or [])
paths.append('relative/path/to/note.md')
doc.obsidian_note_paths = paths
if not doc.reviewed_at:
    doc.reviewed_at = datetime.now()
session.commit()
print(f'obsidian_note_paths: {doc.obsidian_note_paths}')
print(f'reviewed_at: {doc.reviewed_at}')
session.close()
"@
```

**B) `DocumentChunk` — update when note was created from a specific chunk (chunk-based flow):**

For each chunk whose content was used to create/update an Obsidian note, save the note path in `chunk.obsidian_note_paths` so future listing shows which chunks already have notes:

```powershell
cd C:\Users\ziutus\git\_lenie-all\lenie-server-2025\backend; .venv/Scripts/python -c @"
from library.db.engine import get_session
from library.db.models import DocumentChunk
session = get_session()
chunk = session.query(DocumentChunk).filter_by(run_id=<RUN_ID>, position=<POSITION>).first()
paths = list(chunk.obsidian_note_paths or [])
if 'relative/path/to/note.md' not in paths:
    paths.append('relative/path/to/note.md')
chunk.obsidian_note_paths = paths
chunk.status = 'approved'
session.commit()
print(f'chunk #{chunk.position} obsidian_note_paths: {chunk.obsidian_note_paths}')
session.close()
"@
```

If one chunk contributed to multiple notes, append all relevant paths.
If multiple chunks contributed to the same note, update each chunk separately.

**For multi-note sessions (YouTube chunks):** do both A and B after each note is saved, or batch all at once at the end of the session.

Report the updated `obsidian_note_paths` and `reviewed_at` to confirm success.

### Step 7: Update cross-references (if applicable)

If the article topic relates to existing notes (e.g., country files, topic notes), add a brief entry with a link to the new note using `[[Note Name]]` syntax. Also update notes about countries/organizations mentioned in the article (e.g., if the article mentions Russia or China cooperation, update Rosja.md and Chiny.md too).

## Important

- All notes and communication in **Polish**
- Obsidian vault root: `C:\Users\ziutus\Obsydian\personal`
- Knowledge directory: `C:\Users\ziutus\Obsydian\personal\02-wiedza`
- **NEVER use `uv run`** — it does not work in this project (hatchling build error)
- Run Python commands via **PowerShell** with absolute cd: `cd C:\Users\ziutus\git\_lenie-all\lenie-server-2025\backend; .venv/Scripts/python ...` — cd to absolute path is idempotent (works regardless of current directory; never use `cd backend &&` in Bash which fails when CWD is already backend)
- **Steps 1a/1b/1c/2a/4 (including its on-demand trigger) read/write the database via the REST API** on the NAS backend (`http://192.168.200.7:5055`), not via direct ORM/SQLAlchemy access from Windows — every call needs the `x-api-key` header set to `$env:LENIE_API_KEY` (a `kind=service` key created via `imports/api_key_admin.py create --kind service`; set once in your PowerShell profile, e.g. `notepad $PROFILE` — never hardcode the plaintext key in this file or in a command). If the variable is unset, `Invoke-RestMethod` will 401 — ask the user to set it before retrying. Step 6's DB writes are the only remaining direct-DB (ORM) calls in this skill — `--review`/`--list`/`--show`/`--notes` modes of `article_browser.py` are unrelated interactive tools, unaffected by this migration.
- **Step 4b needs a second key**, `$env:LENIE_API_KEY_USER` (a `kind=user` key, e.g. created via `imports/api_key_admin.py create --kind user --user-id <id> --name obsidian-note-fragments`) — the reader-notes endpoint (`GET /document/<id>/notes`) is gated to user keys and 403s for the `kind=service` `$env:LENIE_API_KEY` used everywhere else. Set once in the PowerShell profile alongside `$env:LENIE_API_KEY`, never hardcoded here.
- Always include source with Lenie AI **uuid** (not numeric id) — `doc.uuid` from database
- **Always propose note content before saving** — wait for user approval
- **Financial angle is mandatory** for tech/geopolitics/project notes — include or mark as TODO
- **Prefer chunks over raw text** — when Step 1b finds analysis runs, always use the chunk-based flow (Step 2a); it uses pre-reviewed summaries and saves significant LLM token cost
