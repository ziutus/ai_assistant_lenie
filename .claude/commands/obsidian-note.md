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

**Step 1a — metadata only (no text field, cheap):**

```powershell
cd C:\Users\ziutus\git\_lenie-all\lenie-server-2025\backend; .venv/Scripts/python imports/article_browser.py --meta --id <ARTICLE_ID>
```

Display the metadata to the user.

**Step 1b — Check for chunk analysis runs (all document types)**

Every document type can have chunk analysis runs — mode `transcript` (youtube/movie STT with rewrite) or mode `article` (webpage/link/text/book chapters, no rewrite). Always run this check, regardless of `document_type`.

A document can have **more than one run** (a book typically has one `split_only` run over the whole text plus one `article` run per chapter). List all runs first:

```powershell
cd C:\Users\ziutus\git\_lenie-all\lenie-server-2025\backend; .venv/Scripts/python -c @"
from library.db.engine import get_session
from library.db.models import DocumentAnalysisRun, DocumentChunk
session = get_session()
runs = session.query(DocumentAnalysisRun).filter_by(document_id=<ARTICLE_ID>).order_by(DocumentAnalysisRun.created_at.desc()).all()
if not runs:
    print('NO_RUNS')
else:
    for run in runs:
        chunks = session.query(DocumentChunk).filter_by(run_id=run.id).all()
        temat = [c for c in chunks if c.type == 'TEMAT']
        analyzed = [c for c in temat if c.topic]
        approved = [c for c in temat if c.status == 'approved']
        scope = run.scope or '(caly dokument)'
        created = run.created_at.strftime(chr(37)+\"Y-\"+chr(37)+\"m-\"+chr(37)+\"d\")
        print(f'RUN_ID={run.id}|MODE={run.mode}|STATUS={run.status}|SCOPE={scope}|MODEL={run.model}|CREATED={created}|TEMAT={len(temat)}|ANALYZED={len(analyzed)}|APPROVED={len(approved)}')
session.close()
"@
```

**Interpret the result:**
- `NO_RUNS` → proceed to **Step 1c** (fetch full text via `--dump`)
- **One run** → auto-select it as `<RUN_ID>`, proceed straight to **Step 2a**
- **Multiple runs** → this is typically a book (chapter runs) or a document re-analyzed several times. Show the list to the user (id, mode, scope, temat/analyzed/approved counts). A run with `ANALYZED=0` is a `split_only` run — chunks exist but have no topic/summary yet, not usable for note-writing on its own (even if `APPROVED` is non-zero — that can happen for stale/aborted runs where chunks were approved before topics were ever generated). Propose the run with the highest `ANALYZED` as the default (break ties by `APPROVED`), but let the user pick a different `RUN_ID` (e.g. a specific chapter). Once a `RUN_ID` is chosen, proceed to **Step 2a**.

**Fetch the chunk list for the chosen run** (used by Step 2a — also re-run this after the user picks a different `RUN_ID` from the multi-run list above):

```powershell
cd C:\Users\ziutus\git\_lenie-all\lenie-server-2025\backend; .venv/Scripts/python -c @"
from library.db.engine import get_session
from library.db.models import DocumentAnalysisRun, DocumentChunk
session = get_session()
run = session.get(DocumentAnalysisRun, <RUN_ID>)
chunks = session.query(DocumentChunk).filter_by(run_id=run.id).order_by(DocumentChunk.position).all()
temat = [c for c in chunks if c.type == 'TEMAT']
reklama = [c for c in chunks if c.type != 'TEMAT']  # REKLAMA + SZUM
approved = [c for c in temat if c.status == 'approved']
created = run.created_at.strftime(chr(37)+\"Y-\"+chr(37)+\"m-\"+chr(37)+\"d\")
print(f'RUN_ID={run.id}|MODE={run.mode}|SCOPE={run.scope or \"(caly dokument)\"}|MODEL={run.model}|CREATED={created}')
print(f'TEMAT={len(temat)}|REKLAMA_SZUM={len(reklama)}|APPROVED={len(approved)}')
print('---CHUNKS---')
for c in temat:
    summary = (c.summary or '(brak)').replace(chr(10), ' ')[:250]
    notes = ','.join(c.obsidian_note_paths or [])
    print(f'pos={c.position}|status={c.status}|notes={notes}|topic={c.topic or \"(brak)\"}|summary={summary}')
session.close()
"@
```

If `MODE=article`, `corrected_text` is expected to be `None` for every chunk — that is normal for this mode (no rewrite step), not a data quality issue. See the note in Step 2a's "Content usage rules".

**Step 1c — Fetch full text (only when no chunks exist):**

Check `document_type` from Step 1a to decide the rule:

**For `youtube` or `movie`:**
- Transcription is stored in `text` in the DB regardless of state — `--dump` always returns it.
- If `text_length` from `--meta` is 0 → warn: "Brak transkrypcji dla tego dokumentu YouTube. Nie można utworzyć notatki."
- Otherwise → proceed directly to `--dump`.

**For `webpage`, `link`, or other types:**
- If `document_state` is `URL_ADDED` or `DOCUMENT_INTO_DATABASE` → **STOP and warn the user**:
  > "Artykuł ma status `{state}` — tekst jest surowy (zawiera szum nawigacyjny strony, reklamy itp.) i zużyje znacznie więcej tokenów niż czysty artykuł. Pobierać mimo to?"
  Proceed only if user confirms.
- If `document_state` is `DOCUMENT_CLEANED` or any later state → proceed to `--dump`.

```powershell
cd C:\Users\ziutus\git\_lenie-all\lenie-server-2025\backend; .venv/Scripts/python imports/article_browser.py --dump --id <ARTICLE_ID>
```

The `--dump` JSON adds one extra field to `--meta`: `text` (full article content).

### Step 2a: Chunk-based flow (document has existing analysis chunks)

**Use this step whenever Step 1b found a run to use** (any document type — youtube/movie transcript chunks or webpage/link/text/book article chunks). This is the primary path whenever pre-reviewed chunks exist — it skips sending the full text to the LLM.

**If `TEMAT` count is large (> 30 chunks — same threshold as the `/chunks/:id` UI's `SECTION_VIEW_THRESHOLD`), use the section-grouped view below instead of the flat list.** Typical case: books with a run per chapter, or a `split_only` whole-book run. Otherwise skip straight to **"Flat chunk list"**.

#### Section-grouped view (large runs — books)

Fetch section stats:

```powershell
cd C:\Users\ziutus\git\_lenie-all\lenie-server-2025\backend; .venv/Scripts/python -c @"
from library.db.engine import get_session
from library.db.models import DocumentAnalysisRun, DocumentChunk, DocumentTopicSection
session = get_session()
run = session.get(DocumentAnalysisRun, <RUN_ID>)
chunks = session.query(DocumentChunk).filter_by(run_id=run.id).order_by(DocumentChunk.position).all()
sections = session.query(DocumentTopicSection).filter_by(run_id=run.id).order_by(DocumentTopicSection.position).all()
covered = set()
for s in sections:
    positions = set(s.chunk_positions or [])
    covered |= positions
    members = [c for c in chunks if c.position in positions and c.type == 'TEMAT']
    done = sum(1 for c in members if c.obsidian_note_paths or c.status == 'skipped')
    print(f'SEC_ID={s.id}|pos={s.position}|title={s.title or \"(brak tytulu)\"}|temat={len(members)}|done={done}')
uncovered = [c for c in chunks if c.type == 'TEMAT' and c.position not in covered]
if uncovered:
    done = sum(1 for c in uncovered if c.obsidian_note_paths or c.status == 'skipped')
    print(f'SEC_ID=NONE|title=(chunki bez przypisanej sekcji)|temat={len(uncovered)}|done={done}')
session.close()
"@
```

Topic sections don't always cover every `TEMAT` chunk (LLM synthesis is partial) — the `SEC_ID=NONE` line covers the rest, if any.

**Display split into two groups (same top/bottom convention as the flat list):**
- **Sekcje ukończone** (`done == temat`) at the TOP, compact one-liners: `Rozdział N: Tytuł — ✓ wszystkie opracowane (n tematów)`
- **Sekcje do opracowania** (`done < temat`) at the BOTTOM: `Rozdział N: Tytuł — X/Y opracowanych`

**Ask the user** which section(s) to drill into (by `SEC_ID`, or title). Then for each chosen section, fetch its chunks:

```powershell
cd C:\Users\ziutus\git\_lenie-all\lenie-server-2025\backend; .venv/Scripts/python -c @"
from library.db.engine import get_session
from library.db.models import DocumentChunk, DocumentTopicSection
session = get_session()
section = session.get(DocumentTopicSection, <SEC_ID>)
positions = set(section.chunk_positions or [])
chunks = session.query(DocumentChunk).filter(
    DocumentChunk.run_id == <RUN_ID>,
    DocumentChunk.position.in_(positions),
    DocumentChunk.type == 'TEMAT',
).order_by(DocumentChunk.position).all()
for c in chunks:
    summary = (c.summary or '(brak)').replace(chr(10), ' ')[:250]
    notes = ','.join(c.obsidian_note_paths or [])
    print(f'pos={c.position}|status={c.status}|notes={notes}|topic={c.topic or \"(brak)\"}|summary={summary}')
session.close()
"@
```

(For `SEC_ID=NONE`, filter `DocumentChunk.position.notin_(covered)` instead, reusing the `covered` set logic from the stats query above.)

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

**For each selected chunk — fetch full text from DB (works for both modes):**

```powershell
cd C:\Users\ziutus\git\_lenie-all\lenie-server-2025\backend; .venv/Scripts/python -c @"
from library.db.engine import get_session
from library.db.models import DocumentChunk
session = get_session()
positions = [<comma_separated_positions>]
chunks = session.query(DocumentChunk).filter(
    DocumentChunk.run_id == <RUN_ID>,
    DocumentChunk.position.in_(positions)
).order_by(DocumentChunk.position).all()
for c in chunks:
    print(f'=== CHUNK #{c.position} — {c.topic or \"(brak tematu)\"} ===')
    print(c.corrected_text or c.original_text or '(brak tekstu)')
    print()
session.close()
"@
```

**Content usage rules:**
- If chunk has `summary` and `approved` status → use `summary` as the basis, enrich only if needed
- If chunk needs detail:
  - **mode=transcript** (youtube/movie) → use `corrected_text` (cleaned STT transcript with fillers/rewrite applied). Never send raw `original_text` to the LLM if `corrected_text` is available.
  - **mode=article** (webpage/link/text/book) → `corrected_text` is **always `None` by design** — this mode has no rewrite step, the source markdown is already clean. Use `original_text` directly; this is expected behavior, not missing data, and should NOT be flagged as a data quality issue to the user.
- If chunk is `pending`/`needs_reanalysis` → warn user and ask if they want to proceed anyway (this is a status-based check, orthogonal to which text field is populated)

**Then proceed to Step 3** (find related notes).

### Step 2b: Standard content flow (no existing chunks)

**Use this step when:** the document has no chunk analysis runs at all (Step 1b returned `NO_RUNS`) — regardless of document type. Since Step 1b now checks every type, this step mainly applies to documents that were never run through `/analyze_chunks` yet.

Check `document_type` and `text_length` from `--dump`:

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

Check the `tags` field from the metadata (Step 1a `--meta` output).

If `tags` is non-empty, fetch only the relevant control questions by running:

```powershell
cd C:\Users\ziutus\git\_lenie-all\lenie-server-2025\backend; .venv/Scripts/python imports/control_questions.py --tags <tags_from_dump>
```

For example, if `tags` is `wojsko,gospodarka,sojusze`:
```powershell
cd C:\Users\ziutus\git\_lenie-all\lenie-server-2025\backend; .venv/Scripts/python imports/control_questions.py --tags wojsko,gospodarka,sojusze
```

The script returns only the `##` sections from the control questions file that are relevant to those tags — a small, focused subset instead of the full list.

Then check which of the returned questions are **answered** by the article/chunks. Report only the ones that are answered — skip those with no data.

If any questions are answered, include those answers explicitly in the notes (as dedicated `##` sections matching the question topic, e.g. `## Aspiracje i cele strategiczne`, `## Konflikty`, `## Stan finansów`).

If `tags` is empty, skip this step entirely.

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
- Source line at the end: `Źródło: [Title](URL) (Lenie AI uuid=UUID)` — use the `uuid` field from `--meta` output (NOT the numeric `id`)

**For chunk-based notes (Step 2a):** Add a reference to the chunk topic at the end of the source line if it covers a specific chunk, e.g.: `Źródło: [Title](URL) (Lenie AI uuid=UUID, chunk #3 — "Sytuacja gospodarcza")`

**After creating/updating the note — update `_index.md` if needed:**
- If the note is a **new file** OR its topic has **no matching entry** in `_index.md` → add a line to the appropriate section in `_index.md` (keywords → path)
- If the note already exists in the index → skip
- `_index.md` is already in context from Step 3, so no extra read needed

### Step 6: Update database (MANDATORY — never skip)

After creating/updating Obsidian notes, ALWAYS update the database. Two objects need updating:

**A) `WebDocument` — always update:**

```powershell
cd C:\Users\ziutus\git\_lenie-all\lenie-server-2025\backend; .venv/Scripts/python -c @"
from datetime import datetime
from library.db.engine import get_session
from library.db.models import WebDocument
session = get_session()
doc = WebDocument.get_by_id(session, <ARTICLE_ID>)
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
- Always include source with Lenie AI **uuid** (not numeric id) — `doc.uuid` from database
- **Always propose note content before saving** — wait for user approval
- **Financial angle is mandatory** for tech/geopolitics/project notes — include or mark as TODO
- **Prefer chunks over raw text** — when Step 1b finds analysis runs, always use the chunk-based flow (Step 2a); it uses pre-reviewed summaries and saves significant LLM token cost
