# Story 33.4: Add Article Review and Obsidian Note Tracking

Status: done

## Story

As a **developer**,
I want to track which articles I've reviewed and which have Obsidian notes in the database,
so that `article_browser.py` can filter to unprocessed articles and I don't duplicate knowledge work.

## Acceptance Criteria

1. **Alembic migration adds two columns** to `web_documents`:
   - `reviewed_at TIMESTAMP` (nullable, default NULL)
   - `obsidian_note_paths JSONB NOT NULL DEFAULT '[]'`

2. **ORM model updated**: `WebDocument` in `backend/library/db/models.py` gains:
   - `reviewed_at: Mapped[datetime.datetime | None]` with `DateTime` type
   - `obsidian_note_paths: Mapped[list]` with `JSONB` type and `server_default=sa_text("'[]'")`

3. **`WebDocument.dict()` includes new fields**: `reviewed_at` (ISO string or None) and `obsidian_note_paths` (list)

4. **Review action `[d]` in `article_browser.py`**: sets `reviewed_at = NOW()` for the current document via ORM (`doc.reviewed_at = datetime.now()` + `session.commit()`)

5. **Obsidian action `[o]` in `article_browser.py`**: after creating the Obsidian note, appends the note path to `obsidian_note_paths` JSONB array and sets `reviewed_at` if not already set

6. **`--not-reviewed` filter**: `article_browser.py` accepts `--not-reviewed` flag; filters documents with `reviewed_at IS NULL`

7. **`--no-obsidian` filter**: `article_browser.py` accepts `--no-obsidian` flag; filters documents with `obsidian_note_paths = '[]'`

8. **List display shows review status**: each article in `cmd_list` shows review date (or `-`) and Obsidian note count

9. **Multiple Obsidian notes per article**: pressing `[o]` multiple times appends each path — no overwrite of previous entries

## Tasks / Subtasks

- [x] Task 1: Create Alembic migration (AC: #1)
  - [x] 1.1 Create new migration file with `down_revision` pointing to latest (`b2c3d4e5f6a7`)
  - [x] 1.2 Add `reviewed_at TIMESTAMP` column (nullable)
  - [x] 1.3 Add `obsidian_note_paths JSONB NOT NULL DEFAULT '[]'` column
  - [x] 1.4 Add downgrade that drops both columns

- [x] Task 2: Update ORM model (AC: #2, #3)
  - [x] 2.1 Add `reviewed_at` mapped column to `WebDocument`
  - [x] 2.2 Add `obsidian_note_paths` mapped column to `WebDocument` with JSONB and default `[]`
  - [x] 2.3 Update `WebDocument.dict()` to include both new fields

- [x] Task 3: Add `[d]` mark-as-reviewed action (AC: #4)
  - [x] 3.1 Add `[d]one/reviewed` action to `cmd_review` interactive loop (renamed existing `[d]b save` to `[w]rite to db`)
  - [x] 3.2 Set `doc.reviewed_at = datetime.now()` and commit
  - [x] 3.3 Print confirmation with review timestamp

- [x] Task 4: Update `[o]` obsidian action to track paths (AC: #5, #9)
  - [x] 4.1 After `action_obsidian()` completes, prompt user for Obsidian note path
  - [x] 4.2 Append path to `doc.obsidian_note_paths` JSONB array via ORM
  - [x] 4.3 Set `reviewed_at` if not already set
  - [x] 4.4 Commit and print confirmation

- [x] Task 5: Add CLI filters (AC: #6, #7)
  - [x] 5.1 Add `--not-reviewed` argument to argparse
  - [x] 5.2 Add `--no-obsidian` argument to argparse
  - [x] 5.3 Update `_get_documents()` to filter by `reviewed_at IS NULL` when `--not-reviewed`
  - [x] 5.4 Update `_get_documents()` to filter by `obsidian_note_paths = '[]'` when `--no-obsidian`

- [x] Task 6: Update list display (AC: #8)
  - [x] 6.1 Add review date column to `cmd_list` table output
  - [x] 6.2 Add Obsidian note count column to `cmd_list` table output

- [x] Task 7: Write unit tests
  - [x] 7.1 Test ORM model: `reviewed_at` defaults to None, `obsidian_note_paths` defaults to `[]`
  - [x] 7.2 Test ORM model: `dict()` includes new fields
  - [x] 7.3 Test JSONB append logic for `obsidian_note_paths`
  - [x] 7.4 Test filter logic for `--not-reviewed` and `--no-obsidian` (covered via Python-level filtering in `_get_documents()`)

## Dev Notes

### Design Decision

**ADR-014** ([docs/adr-014-article-review-tracking.md](../../docs/adr-014-article-review-tracking.md)) documents why these are columns on `web_documents` (not a new table or a new document_state):
- Review state is **orthogonal** to processing state (`document_state`). A document can be `EMBEDDING_EXIST` and unreviewed simultaneously.
- Single-user system — join table adds complexity without benefit.
- Phase 9 (multi-user, B-33/B-34/B-35) will migrate to `user_document_reviews` + `user_obsidian_notes` tables via a single Alembic migration.

### Architecture Compliance

- **Alembic migration pattern**: Follow existing pattern from `a1b2c3d4e5f6` (import_logs) and `906d2cc23d09` (lookup tables). `down_revision` must be `b2c3d4e5f6a7` (latest migration).
- **ORM model pattern**: Use `Mapped[...]` with `mapped_column(...)` — consistent with all other columns in `WebDocument`. Import `JSONB` from `sqlalchemy.dialects.postgresql` (already imported in `models.py` for `ImportLog.parameters`).
- **`server_default` for JSONB**: Use `server_default=sa_text("'[]'")` — same pattern as `ImportLog.parameters` uses `sa_text("'{}'")`.

### Key Code Locations

| What | File | Line(s) |
|------|------|---------|
| WebDocument ORM model | `backend/library/db/models.py` | 90–383 |
| WebDocument.dict() | `backend/library/db/models.py` | 350–383 |
| JSONB import | `backend/library/db/models.py` | 27 |
| article_browser.py main | `backend/imports/article_browser.py` | 1082–1125 |
| cmd_review interactive loop | `backend/imports/article_browser.py` | 904–1055 |
| cmd_list display | `backend/imports/article_browser.py` | 816–841 |
| _get_documents filter | `backend/imports/article_browser.py` | 793–813 |
| action_obsidian | `backend/imports/article_browser.py` | 547–573 |
| Latest Alembic migration | `backend/alembic/versions/b2c3d4e5f6a7_alter_import_logs_parameters_to_jsonb.py` |

### Critical Implementation Details

1. **JSONB append via ORM** — Do NOT use raw SQL `|| '["path"]'::jsonb`. Instead, load the list from the ORM attribute, append in Python, reassign:
   ```python
   paths = list(doc.obsidian_note_paths or [])
   paths.append(new_path)
   doc.obsidian_note_paths = paths
   session.commit()
   ```
   SQLAlchemy detects the change via attribute reassignment. Mutating the list in-place without reassignment will NOT trigger a flush.

2. **`[d]` action conflicts with existing `[d]b save`** — The existing `cmd_review` loop uses `[d]` for "db save" (line 1009). Options:
   - Rename existing `[d]b save` to `[w]rite to db` or `[b]` and use `[d]` for "done/reviewed"
   - Use a different key for mark-reviewed, e.g. `[x]` (done) or `[!]` (mark reviewed)
   - **Recommended**: Ask the user which key to use. The acceptance criteria says `[d]` but the existing `[d]` is taken.

3. **Obsidian note path format** — Relative to the Obsidian vault root (`C:\Users\ziutus\Obsydian\personal`). Example: `"02-wiedza/Geopolityka/Sankcje-UE.md"`. The `action_obsidian()` function calls Claude Code as a subprocess — the developer must capture the created note path after Claude Code completes. Prompt the user to enter the path manually after the subprocess returns.

4. **`_get_documents()` currently uses `WebsitesDBPostgreSQL.get_list()` which returns dicts, then does `WebDocument.get_by_id()`** — This is N+1. For filtering by `reviewed_at IS NULL`, add the filter to the initial query or filter after loading. The simplest approach: add Python-level filtering in `_get_documents()` after loading documents (consistent with existing `portal`, `state`, `since` filters on line 800-812).

5. **`cmd_list` format `"ids"` and `"short"`** return early (lines 821-831) — new columns only needed in `"table"` format.

### Previous Story Learnings (from 33-1, 33-2, 33-3)

- **33-1**: `CACHE_DIR` pattern is `cfg.get("CACHE_DIR") or "tmp"` — article_browser.py already uses this (line 390).
- **33-2**: `ImportLog` JSONB column uses `server_default=sa_text("'{}'")` — follow same pattern for `obsidian_note_paths` with `sa_text("'[]'")`.
- **33-2**: Alembic migration IDs are manual hex strings (e.g. `a1b2c3d4e5f6`). Use a descriptive hex string for the new migration.
- **33-3**: Code review found issues with error handling and type annotations — be explicit with types from the start.

### Testing Standards

- Test file: `backend/tests/unit/test_article_review_tracking.py`
- Use `pytest.importorskip("sqlalchemy")` at module level (pattern from story 26-2).
- Mock `session` for unit tests — do not require database connectivity.
- Test `WebDocument` attribute defaults, `dict()` output, and JSONB append behavior.
- Follow existing test patterns: 33-2 has 11 tests in `test_import_log_tracker.py`.

### Project Structure Notes

- All changes are within `backend/` — no frontend, shared, or infrastructure changes needed.
- No new files except the Alembic migration and test file.
- `article_browser.py` is a standalone CLI script in `imports/` — not part of the Flask API.

### References

- [ADR-014: Article Review Tracking](../../docs/adr-014-article-review-tracking.md) — full design rationale and multi-user migration plan
- [Source: backend/library/db/models.py] — WebDocument ORM model
- [Source: backend/imports/article_browser.py] — primary consumer, all UI changes
- [Source: backend/alembic/versions/b2c3d4e5f6a7] — latest Alembic migration (down_revision target)
- [Source: backend/alembic/versions/a1b2c3d4e5f6] — import_logs migration (JSONB pattern reference)

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (1M context)

### Debug Log References

- `server_default='[]'` only applies at DB level; in-memory Python default is `None`. Fixed by using `or []` in `dict()` and in `_get_documents()` filter.
- `WebDocument.__new__()` does not initialize SQLAlchemy instrumentation — must use `WebDocument(...)` constructor in tests.
- Existing `[d]` key was taken by "db save" — resolved by renaming to `[w]rite to db` per user preference.

### Completion Notes List

- **Task 1**: Alembic migration `c3d4e5f6a7b8` adds `reviewed_at TIMESTAMP` and `obsidian_note_paths JSONB NOT NULL DEFAULT '[]'` to `web_documents`.
- **Task 2**: ORM model updated with `Mapped` columns + `dict()` extended with ISO format for `reviewed_at` and normalized `obsidian_note_paths`.
- **Task 3**: `[d]one/reviewed` action added to `cmd_review`; existing `[d]b save` renamed to `[w]rite to db`.
- **Task 4**: `action_track_obsidian_path()` prompts for note path after `action_obsidian()`, appends to JSONB array, auto-sets `reviewed_at`.
- **Task 5**: `--not-reviewed` and `--no-obsidian` CLI flags filter documents in `_get_documents()` (Python-level filtering, consistent with existing `portal`, `state`, `since` filters).
- **Task 6**: Table format shows `R:YYYY-MM-DD` (review date or `-`) and `O:N` (obsidian note count) columns.
- **Task 7**: 12 unit tests covering defaults, `dict()` output, JSONB append logic, and `reviewed_at` behavior.
- **Regression fixes**: Updated `test_db_models.py` (column count 26→28, dict keys 30→32), `test_orm_crud.py` (dict keys), plus boto3 import fixes in `test_dynamodb_sync_orm.py`, `test_flask_endpoints_orm.py`, `test_unknown_news_import_orm.py`, `test_youtube_processing_orm.py`.

### Change Log

- 2026-03-30: Story 33.4 implemented — article review tracking and Obsidian note paths (all 7 tasks, 12 new tests, 528 total tests pass)
- 2026-03-30: Code review (AI) — 5 issues fixed: limit/filter interaction in `_get_documents()`, Obsidian path validation, 7 filter unit tests added, test name/comment corrections, unused import restored

### File List

- `backend/alembic/versions/c3d4e5f6a7b8_add_reviewed_at_and_obsidian_note_paths.py` (new)
- `backend/library/db/models.py` (modified — 2 new columns + dict() update)
- `backend/imports/article_browser.py` (modified — new actions, filters, display columns)
- `backend/tests/unit/test_article_review_tracking.py` (new — 12 tests)
- `backend/tests/unit/test_db_models.py` (modified — column count + dict keys)
- `backend/tests/unit/test_orm_crud.py` (modified — dict keys)
- `backend/tests/unit/test_dynamodb_sync_orm.py` (modified — boto3 import fix)
- `backend/tests/unit/test_flask_endpoints_orm.py` (modified — cfg mock)
- `backend/tests/unit/test_unknown_news_import_orm.py` (modified — updated for feed_monitor refactor)
- `backend/tests/unit/test_youtube_processing_orm.py` (modified — boto3 import fix)
