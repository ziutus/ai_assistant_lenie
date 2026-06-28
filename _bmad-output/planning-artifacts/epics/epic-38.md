## Epic 38: Obsidian Tools + Note Version History

Developer can read, create, update, list, and delete notes in the Obsidian vault restricted to `02-wiedza/` via MCP — with automatic versioning before every write, audit history retrieval, and full path traversal prevention.

**Stories:** 38-1, 38-2, 38-3, 38-4, 38-5

Implementation notes:
- Story 38-1 (obsidian_note_versions table — Alembic migration) must be completed first — Stories 38-3 and 38-5 depend on it
- Stories 38-2 (read/list) and 38-4 (delete) are independent and can be done in parallel
- Story 38-3 (obsidian_write_note with versioning) depends on 38-1 AND on Epic 37 Story 37-2 (linking helpers)
- Story 38-5 (history) depends on 38-1

### Story 38.1: obsidian_note_versions Table — Alembic Migration

As a **developer**,
I want a `obsidian_note_versions` table that automatically captures note content before every MCP write operation,
so that every note change is auditable and recoverable, with the user prompt preserved for quality review.

**Acceptance Criteria:**

**Given** no `obsidian_note_versions` table exists
**When** the developer creates an Alembic migration in `backend/alembic/`
**Then** the migration creates the table:
```sql
CREATE TABLE obsidian_note_versions (
    id          SERIAL PRIMARY KEY,
    note_path   TEXT NOT NULL,
    content_before TEXT,
    content_after  TEXT NOT NULL,
    user_prompt    TEXT,
    article_id     INTEGER REFERENCES web_documents(id) ON DELETE SET NULL,
    changed_by     TEXT NOT NULL DEFAULT 'mcp_server',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_obsidian_versions_note_path ON obsidian_note_versions(note_path, created_at DESC);
```

**Given** the migration exists
**When** `alembic upgrade head` is run against the NAS PostgreSQL
**Then** the table and index are created without errors

**Given** the migration is applied
**When** `alembic downgrade -1` is run
**Then** the table and index are dropped cleanly

**Given** an article is deleted from `web_documents`
**When** the cascade fires
**Then** `obsidian_note_versions.article_id` is set to NULL (ON DELETE SET NULL) — version history is preserved

**Technical notes:**
- SQLAlchemy ORM model `ObsidianNoteVersion` added to `backend/library/db/models.py`
- `content_before` is nullable — NULL for new notes (no prior content)
- Migration file in `backend/alembic/versions/` following existing naming convention
- `.venv_wsl` must be synced after migration (see CLAUDE.md dependency checklist)

### Story 38.2: obsidian_read_note & obsidian_list_notes Tools

As a **user on mobile**,
I want to read existing Obsidian notes and browse available notes in a folder,
so that I can see what I've already written before deciding what to add or update.

**Acceptance Criteria:**

**Given** `OBSIDIAN_VAULT_PATH` is set to `/vault` and a note exists at `/vault/02-wiedza/Kraje/Turcja/Polityka.md`
**When** `obsidian_read_note(note_path="02-wiedza/Kraje/Turcja/Polityka.md")` is invoked
**Then** the tool returns the full markdown content of the file as a string

**Given** a path outside `02-wiedza/` is requested (e.g. `"../journal/today.md"`, `"/etc/passwd"`, `"02-other/note.md"`)
**When** `obsidian_read_note` is invoked
**Then** it returns error `{"error": "note_path_invalid", "message": "Ścieżka jest poza dozwolonym obszarem 02-wiedza/."}`
**And** the attempt is logged at WARNING level with the rejected path

**Given** the requested path is within `02-wiedza/` but the file does not exist
**When** `obsidian_read_note` is invoked
**Then** it returns error `{"error": "note_not_found", "message": "Nie ma notatki pod tą ścieżką w 02-wiedza/."}`

**Given** `obsidian_list_notes(folder="02-wiedza/Kraje/Turcja")` is invoked
**When** the folder exists
**Then** it returns a list of note objects, each with:
- `path` (relative to vault root, e.g. `"02-wiedza/Kraje/Turcja/Polityka.md"`)
- `name` (filename without extension, e.g. `"Polityka"`)
- `size_kb` (integer)
- `modified_at` (ISO 8601 string)

**Given** `obsidian_list_notes()` is invoked with no folder parameter
**When** the tool runs
**Then** it lists all notes recursively under `02-wiedza/` (up to 200 items — pagination not required for MVP)

**Given** `obsidian_list_notes` is called on a folder that does not exist
**When** the tool runs
**Then** it returns an empty list (not an error — folder may be created later)

**Technical notes:**
- Path validation: resolved path must start with `{OBSIDIAN_VAULT_PATH}/02-wiedza/` — use `os.path.realpath()` to prevent symlink escapes
- `obsidian_list_notes` uses `os.walk()` restricted to `02-wiedza/` subtree
- Only `.md` files are returned by `obsidian_list_notes` (ignore `.DS_Store`, `.obsidian/`, etc.)
- Tool parameters: `obsidian_read_note(note_path: str)`, `obsidian_list_notes(folder: str = "02-wiedza")`

### Story 38.3: obsidian_write_note Tool — Create/Update with Automatic Versioning

As a **user on mobile**,
I want Claude to create or update an Obsidian note in my vault,
so that my knowledge base grows from article reviews without needing to touch the computer — and every change is versioned for safety.

**Acceptance Criteria:**

**Given** `obsidian_write_note(note_path="02-wiedza/Kraje/Turcja/Polityka.md", content="# Polityka Turcji\n...", user_prompt="Dodaj sekcję o sankcjach")` is invoked
**When** the write succeeds
**Then** the following sequence happens atomically:
  1. Content of existing file (or NULL if new) is read from disk
  2. A row is inserted into `obsidian_note_versions` with `content_before`, `content_after=content`, `user_prompt`, `note_path`
  3. The file is written to disk at `{OBSIDIAN_VAULT_PATH}/note_path`
**And** the tool returns `{"written": true, "path": "02-wiedza/Kraje/Turcja/Polityka.md", "is_new": <bool>}`

**Given** `version_save` to database fails before the file is written
**When** the error occurs
**Then** the file is NOT written to disk
**And** error `{"error": "version_save_failed", "message": "Wstrzymałem zapis notatki — nie mogłem zapisać wersji historycznej. Notatka nie została zmieniona."}` is returned
**And** the failed attempt is logged at ERROR level (NFR9 — no overwrite without version save)

**Given** the file write fails after version save succeeds (e.g. disk full)
**When** the error occurs
**Then** error `{"error": "vault_write_failed", "message": "Nie udało się zapisać notatki — sprawdź miejsce na dysku i status Obsidian Sync."}` is returned
**And** the `obsidian_note_versions` row remains in the DB (partial state documented — content was saved but not written)

**Given** the note path is outside `02-wiedza/`
**When** `obsidian_write_note` is invoked
**Then** it returns `{"error": "note_path_invalid", ...}` — same validation as `obsidian_read_note`

**Given** `obsidian_write_note` is called with `article_id=42` and `mark_as_reviewed=True`
**When** the write succeeds
**Then** `append_obsidian_note_path(session, 42, note_path)` is called (from Epic 37, Story 37-2)
**And** `mark_article_reviewed(session, 42)` is called in the same database transaction

**Given** the parent directory of the note path does not exist (e.g. `02-wiedza/NewCountry/` is a new folder)
**When** `obsidian_write_note` is invoked
**Then** the directory is created automatically (`os.makedirs(..., exist_ok=True)`)

**Performance requirement:** Write operation (including version save) completes within 3 seconds (NFR3).

**Technical notes:**
- Tool parameters: `note_path: str`, `content: str`, `user_prompt: str | None = None`, `article_id: int | None = None`, `mark_as_reviewed: bool = False`
- `is_new` in response: `True` if the file did not exist before write
- Version save uses the MCP server's own DB session (shared PostgreSQL on `lenie-net`)
- File write: `open(resolved_path, "w", encoding="utf-8")` — UTF-8 always (Obsidian default)

### Story 38.4: obsidian_delete_note Tool

As a **user on mobile**,
I want to delete an Obsidian note via Claude,
so that I can remove outdated or incorrect notes from my knowledge base.

**Acceptance Criteria:**

**Given** a note exists at `02-wiedza/Stare/outdated.md`
**When** `obsidian_delete_note(note_path="02-wiedza/Stare/outdated.md")` is invoked
**Then** the file is deleted from the filesystem
**And** the tool returns `{"deleted": true, "path": "02-wiedza/Stare/outdated.md"}`

**Given** the note path does not exist
**When** `obsidian_delete_note` is invoked
**Then** it returns error `{"error": "note_not_found", "message": "Nie ma notatki pod tą ścieżką w 02-wiedza/."}`

**Given** the note path is outside `02-wiedza/`
**When** `obsidian_delete_note` is invoked
**Then** it returns `{"error": "note_path_invalid", ...}`

**Given** a note is deleted
**When** the operation completes
**Then** no new row is inserted into `obsidian_note_versions` (deletes are not versioned in MVP)
**And** existing version history rows for that path remain in the DB (they are not purged)

**Technical notes:**
- Tool parameter: `note_path: str`
- Uses `os.remove(resolved_path)` — does not delete empty parent directories
- Versioning of deletes is a post-MVP feature

### Story 38.5: obsidian_note_history Tool

As a **user on mobile**,
I want to see the history of changes made to an Obsidian note by Claude,
so that I can understand how the note evolved and verify that changes were correct.

**Acceptance Criteria:**

**Given** a note at `02-wiedza/Kraje/Turcja/Polityka.md` has been written multiple times by the MCP server
**When** `obsidian_note_history(note_path="02-wiedza/Kraje/Turcja/Polityka.md")` is invoked
**Then** it returns a list of version records (newest first, default limit 10), each containing:
- `id` (integer)
- `changed_at` (ISO 8601 string — maps to `created_at`)
- `user_prompt` (string or null — what the user asked Claude to do)
- `article_id` (integer or null — source article if linked)
- `content_before` (string or null — full content before change; null if it was a new note)
- `content_after` (string — full content after change)

**Given** `obsidian_note_history(note_path="...", limit=5)` is invoked
**When** the result is returned
**Then** at most 5 records are returned

**Given** no history exists for a note path
**When** `obsidian_note_history` is invoked
**Then** it returns an empty list (not an error)

**Given** the note path is outside `02-wiedza/`
**When** `obsidian_note_history` is invoked
**Then** it returns `{"error": "note_path_invalid", ...}`

**Given** PostgreSQL is unavailable
**When** `obsidian_note_history` is invoked
**Then** it returns `{"error": "database_unavailable", ...}`

**Technical notes:**
- Tool parameters: `note_path: str`, `limit: int = 10`
- Query: `SELECT * FROM obsidian_note_versions WHERE note_path = :path ORDER BY created_at DESC LIMIT :limit`
- Full `content_before` and `content_after` are returned — large notes may produce large responses; Claude handles truncation if needed
- Path validation applies (same `02-wiedza/` restriction as other tools)
