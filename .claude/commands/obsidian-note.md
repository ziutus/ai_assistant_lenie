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

Execute ALL steps below in order. Do NOT skip step 5 (database update).

### Step 1: Fetch article from database

**Step 1a — metadata only (no text field, cheap):**

```powershell
cd C:\Users\ziutus\git\_lenie-all\lenie-server-2025\backend; .venv/Scripts/python imports/article_browser.py --meta --id <ARTICLE_ID>
```

Display the metadata to the user.

**Step 1b — check `document_state` before fetching text:**

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

### Step 2: Detect content type and plan approach

**Before anything else**, check `document_type` and `text_length`:

#### Long YouTube video (document_type == "youtube" AND text_length > 10 000)

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

If the article is about **geopolitics** (countries, wars, alliances, military, diplomacy, regions), read the control questions file:

`C:\Users\ziutus\Obsydian\personal\02-wiedza\Geopolityka i polityka\_pytania_kontrolne\_Pytania do każdego kraju czy obszaru.md`

Then check which of the questions below are answered by the article. Report only the ones that **are** answered — skip those with no data:

- **Czyja to strefa wpływu / do jakiego bloku należy?** — USA, Russia, China orbit? Non-aligned?
- **Czyjej technologii używa?** — whose weapons, internet infrastructure, nuclear reactors?
- **Z kim prowadzi konflikty i na jakim poziomie?** — political / proxy / traditional war
- **Jaka ma armię w porównaniu do innych?** — arms imports, capabilities, suppliers
- **Jakie ma aspiracje i cele strategiczne?** — what does the country want to achieve?
- **Jaki jest stan finansów?** — rich, bankrupt, dependent on commodities?
- **Czy jest regionalnym hegemonem?** — does it dominate the region militarily/politically?
- **Jaka panuje ideologia?** — imperialism, nationalism, theocracy, democracy?
- **Jakie są strefy buforowe?** — which countries/territories act as buffers?
- **Czy kraj jest bliski rewolucji?** — internal stability?
- **Jaka rolę pełni w systemie międzynarodowym?** — mediator, supplier, client state?

If any questions are answered, include those answers explicitly in the notes when creating/updating them (as dedicated `##` sections matching the question topic, e.g. `## Aspiracje i cele strategiczne`, `## Konflikty`, `## Stan finansów`).

If the article is **not** about geopolitics, skip this step entirely.

### Step 5: Discuss with user and create/update notes

Present the user with:
- Summary of the article (3-5 key points in Polish)
- Found related Obsidian notes
- Which control questions are answered (if geopolitics article)
- Proposal: create new note, update existing, or both

**Financial angle (always check):** For every note about technology, geopolitics, projects or companies — explicitly ask or include: kto finansuje, ile to kosztuje, skąd pochodzi zwrot z inwestycji, jaka jest skala rynku. If data is missing — mark as `TODO: wątek finansowy`. Bez pieniędzy nie ma efektów.

Wait for user input on what to create/update. Then create/update the Obsidian .md files following vault conventions:
- Frontmatter with tags (`tags: wiedza/...`)
- H1 heading
- Content with `##` sections, `**bold**` for key points
- Obsidian wiki-links `[[Country]]` for cross-references
- Source line at the end: `Źródło: [Title](URL) (Lenie AI uuid=UUID)` — use the `uuid` field from `--dump` output (NOT the numeric `id`)

**After creating/updating the note — update `_index.md` if needed:**
- If the note is a **new file** OR its topic has **no matching entry** in `_index.md` → add a line to the appropriate section in `_index.md` (keywords → path)
- If the note already exists in the index → skip
- `_index.md` is already in context from Step 3, so no extra read needed

### Step 6: Update database (MANDATORY — never skip)

After creating/updating Obsidian notes, ALWAYS update the article in the database.
Use article_browser.py's ORM session pattern:

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

**For multi-note sessions (YouTube):** append paths one by one after each note is saved, OR append all at once at the end of the session.

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
