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

## Workflow

Execute ALL steps below in order. Do NOT skip step 4 (database update).

### Step 1: Fetch article from database

Use article_browser.py `--dump` mode — it outputs UTF-8 JSON with all metadata and full text:

```bash
cd backend && .venv/Scripts/python imports/article_browser.py --dump --id <ARTICLE_ID>
```

The JSON contains: `id`, `title`, `url`, `created_at`, `document_state`, `document_type`, `language`, `source`, `author`, `reviewed_at`, `obsidian_note_paths`, `text_length`, `text`.

Display article metadata to the user.

### Step 2: Search Obsidian vault for related notes

Search `C:\Users\ziutus\Obsydian\personal\02-wiedza` using Grep and Glob for notes related to the article's topic:
1. First search country files in `Kraje/**/*.md` (Glob + Grep)
2. Then search by keywords from the article title and content
3. Report what was found

### Step 3: Discuss with user and create/update notes

Present the user with:
- Summary of the article (3-5 key points in Polish)
- Found related Obsidian notes
- Proposal: create new note, update existing, or both

Wait for user input on what to create/update. Then create/update the Obsidian .md files following vault conventions:
- Frontmatter with tags (`tags: wiedza/...`)
- H1 heading
- Content with `##` sections, `**bold**` for key points
- Obsidian wiki-links `[[Country]]` for cross-references
- Source line at the end: `Źródło: [Title](URL) (Lenie AI id=ID)`

### Step 4: Update database (MANDATORY — never skip)

After creating/updating Obsidian notes, ALWAYS update the article in the database.
Use article_browser.py's ORM session pattern:

```bash
cd backend && .venv/Scripts/python -c "
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
"
```

Report the updated `obsidian_note_paths` and `reviewed_at` to confirm success.

### Step 5: Update cross-references (if applicable)

If the article topic relates to existing notes (e.g., country files, topic notes), add a brief entry with a link to the new note using `[[Note Name]]` syntax. Also update notes about countries/organizations mentioned in the article (e.g., if the article mentions Russia or China cooperation, update Rosja.md and Chiny.md too).

## Important

- All notes and communication in **Polish**
- Obsidian vault root: `C:\Users\ziutus\Obsydian\personal`
- Knowledge directory: `C:\Users\ziutus\Obsydian\personal\02-wiedza`
- **NEVER use `uv run`** — it does not work in this project (hatchling build error)
- Run commands from `backend/` dir: `cd backend && .venv/Scripts/python ...`
- Always include source with Lenie AI id
