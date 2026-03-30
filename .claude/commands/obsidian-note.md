# Obsidian Note from Article

Create or update Obsidian notes based on a Lenie DB article, then update the database.

## Input

Article ID: $ARGUMENTS (required — Lenie DB document id)

## Workflow

Execute ALL steps below in order. Do NOT skip step 4 (database update).

### Step 1: Fetch article from database

Run Python via `uv run` in the `backend/` directory to get article content:
- Title, URL, date, state, language, source
- Full text (`text_md` or `text` or `text_raw`)
- Current `reviewed_at` and `obsidian_note_paths` values

Display article metadata to the user.

### Step 2: Search Obsidian vault for related notes

Search `C:\Users\ziutus\Obsydian\personal\02-wiedza` using Grep and Glob for notes related to the article's topic. Check keywords from the article title and content. Report what was found.

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

After creating/updating Obsidian notes, ALWAYS run Python to update the article in the database:

```python
# Append new note paths to obsidian_note_paths
paths = list(doc.obsidian_note_paths or [])
paths.append("relative/path/to/note.md")  # relative to vault root
doc.obsidian_note_paths = paths

# Set reviewed_at if not already set
if not doc.reviewed_at:
    doc.reviewed_at = datetime.now()

session.commit()
```

Report the updated `obsidian_note_paths` and `reviewed_at` to confirm success.

### Step 5: Update cross-references (if applicable)

If the article topic relates to existing notes (e.g., `Wojny dronowe.md`, country files), add a brief entry with a link to the new note using `[[Note Name]]` syntax.

## Important

- All notes and communication in **Polish**
- Obsidian vault root: `C:\Users\ziutus\Obsydian\personal`
- Knowledge directory: `C:\Users\ziutus\Obsydian\personal\02-wiedza`
- Database runs in `backend/` directory, use `uv run` to execute Python
- Always include source with Lenie AI id
