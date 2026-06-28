# Story 36.2: lenie_get_article Tool

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **user on mobile**,
I want to ask Claude to retrieve the full content of a specific article from Lenie,
so that I can read it and decide how to incorporate it into my Obsidian notes.

## Acceptance Criteria

1. **AC-1: Tool registered in FastMCP** — `lenie_get_article` is registered inside `register_lenie_tools` in `backend/mcp_server/tools/lenie.py`. Running the server and listing tools via MCP client reveals `lenie_get_article`.

2. **AC-2: Existing article returns full record** — When invoked with a valid `article_id`, the tool returns a dict containing:
   - `id` (integer — the PK from `web_documents.id`)
   - `title` (string or `null`)
   - `source` (URL string — the `url` column)
   - `size_kb` (integer — `len(text.encode()) // 1024` if `text` is set, else `0`)
   - `content` (string or `null` — the `text` column; full text, no truncation)
   - `language` (string or `null` — e.g. `"pl"`, `"en"`)
   - `user_note` (string or `null` — the `note` column)
   - `document_type` (string — e.g. `"webpage"`, `"youtube"`, `"link"`)
   - `added_at` (ISO 8601 string or `null` — from `created_at` column)
   - `reviewed_at` (ISO 8601 string or `null`)
   - `obsidian_note_paths` (array of strings — `obsidian_note_paths or []`)

3. **AC-3: Article not found → McpError** — When `article_id` does not exist, the tool calls `raise_article_not_found(article_id)` from `mcp_server.errors`, raising `McpError` with code `McpErrorCode.ARTICLE_NOT_FOUND`.

4. **AC-4: Database unavailable → McpError** — When PostgreSQL is unavailable (`OperationalError`), the tool calls `raise_database_unavailable()`, raising `McpError` with code `McpErrorCode.DATABASE_UNAVAILABLE`.

5. **AC-5: Full content returned** — Content of any size (including >100 KB) is returned in full without truncation. No server-side truncation is added.

6. **AC-6: Performance** — Response within 5 seconds for a typical article (single PK lookup).

7. **AC-7: Session cleanup** — `session.close()` is called in a `finally` block, both on success and on error.

8. **AC-8: Quality gates pass** — `cd backend && PYTHONPATH=. uvx pytest tests/unit/ -v` passes unchanged. `cd backend && PYTHONPATH=. .venv/Scripts/python -m pytest mcp_server/tests/unit/ -v` passes. `uvx ruff check backend/mcp_server/` reports no new errors.

## Tasks / Subtasks

- [x] Task 1: Implement `lenie_get_article` in `backend/mcp_server/tools/lenie.py` (AC: 1–7)
  - [x] 1.1 Add `lenie_get_article(article_id: int) -> dict` inside `register_lenie_tools` using `@mcp.tool()` decorator
  - [x] 1.2 Query: `select(WebDocument).where(WebDocument.id == article_id)` + `session.execute(...).scalars().first()`
  - [x] 1.3 If `doc is None`: call `raise_article_not_found(article_id)` (AC: 3)
  - [x] 1.4 Map columns to response dict (see Dev Notes for exact mapping) (AC: 2)
  - [x] 1.5 Wrap DB calls in `try/except OperationalError` → `raise_database_unavailable()` (AC: 4)
  - [x] 1.6 `session = None` before try, `get_session()` inside try, `finally: if session is not None: session.close()` (AC: 7)
  - [x] 1.7 Add `raise_article_not_found` to imports from `mcp_server.errors`

- [x] Task 2: Add unit tests in `backend/mcp_server/tests/unit/test_lenie_tools.py` (AC: 2–7)
  - [x] 2.1 Test: valid article → all required keys present with correct values
  - [x] 2.2 Test: null `text` → `size_kb=0`, `content=None`
  - [x] 2.3 Test: null `reviewed_at` → `reviewed_at=None` in response
  - [x] 2.4 Test: article not found (`.first()` returns `None`) → `McpError` with `ARTICLE_NOT_FOUND` code
  - [x] 2.5 Test: `OperationalError` → `McpError` with `DATABASE_UNAVAILABLE` code
  - [x] 2.6 Test: `session.close()` called on success
  - [x] 2.7 Test: `session.close()` called on `OperationalError`

- [x] Task 3: Run quality gates (AC: 8)
  - [x] 3.1 `cd backend && PYTHONPATH=. uvx pytest tests/unit/ -v` — 70 passed, 27 skipped (no regressions)
  - [x] 3.2 `cd backend && PYTHONPATH=. .venv/Scripts/python -m pytest mcp_server/tests/unit/ -v` — 50 passed (7 new)
  - [x] 3.3 `uvx ruff check backend/mcp_server/` — all checks passed

## Dev Notes

### CRITICAL: Column Name Mapping — Epic vs ORM

This story inherits the same column name discrepancies discovered in Story 36-1:

| Response field | ORM column | Notes |
|----------------|-----------|-------|
| `source` (URL) | `doc.url` | `doc.source` = discovery channel ("own", "unknow.news") — NOT the article URL |
| `content` | `doc.text` | `text_content` does NOT exist in DB/ORM |
| `user_note` | `doc.note` | Direct column access |
| `added_at` | `doc.created_at.isoformat()` | DateTime → ISO 8601 string |
| `reviewed_at` | `doc.reviewed_at.isoformat() if doc.reviewed_at else None` | Nullable DateTime |
| `size_kb` | `len(doc.text.encode()) // 1024 if doc.text else 0` | Computed, not stored |
| `obsidian_note_paths` | `doc.obsidian_note_paths or []` | JSONB, may be `None` in old records |

### Implementation Pattern (FastMCP)

Add `lenie_get_article` **inside** the existing `register_lenie_tools` function — do NOT create a second registration function. Both tools share `@mcp.tool()` decorator under the same `mcp` instance:

```python
# In register_lenie_tools(mcp) — after lenie_unreviewed_articles definition:

@mcp.tool()
def lenie_get_article(article_id: int) -> dict:
    """Return the full content and metadata of a specific article from the Lenie knowledge base.

    Args:
        article_id: Integer primary key from web_documents.id (shown in lenie_unreviewed_articles results).

    Returns:
        dict with full article data including id, title, source, size_kb, content, language,
        user_note, document_type, added_at, reviewed_at, obsidian_note_paths.
    """
    session = None
    try:
        session = get_session()
        doc = session.execute(
            select(WebDocument).where(WebDocument.id == article_id)
        ).scalars().first()

        if doc is None:
            raise_article_not_found(article_id)

        size_kb = len(doc.text.encode()) // 1024 if doc.text else 0
        return {
            "id": doc.id,
            "title": doc.title,
            "source": doc.url,
            "size_kb": size_kb,
            "content": doc.text,
            "language": doc.language,
            "user_note": doc.note,
            "document_type": doc.document_type,
            "added_at": doc.created_at.isoformat() if doc.created_at else None,
            "reviewed_at": doc.reviewed_at.isoformat() if doc.reviewed_at else None,
            "obsidian_note_paths": doc.obsidian_note_paths or [],
        }
    except OperationalError:
        raise_database_unavailable()
    finally:
        if session is not None:
            session.close()
```

### Required Import Change in `lenie.py`

Add `raise_article_not_found` to the existing import:

```python
# Before:
from mcp_server.errors import raise_database_unavailable

# After:
from mcp_server.errors import raise_article_not_found, raise_database_unavailable
```

No other imports needed — `select`, `WebDocument`, `get_session`, `OperationalError` are already imported in the file.

### `raise_article_not_found` Already Exists

`mcp_server.errors` already has `raise_article_not_found(article_id: int)` implemented (code `McpErrorCode.ARTICLE_NOT_FOUND = -32001`). No changes to `errors.py` needed.

### Testing Strategy

Add a new class `TestLenieGetArticle` in the existing `test_lenie_tools.py`. Reuse the `_CaptureMcp` and `_make_doc` helpers already defined in the file. For `lenie_get_article` tests, create a simpler mock session that returns the doc directly (single `session.execute(...).scalars().first()` call):

```python
def _mock_session_single(doc_or_none):
    """Return a mock session for single-document lookup."""
    session = MagicMock()
    result = MagicMock()
    result.scalars.return_value.first.return_value = doc_or_none
    session.execute.return_value = result
    return session
```

Get the tool function:

```python
def _get_get_article_tool():
    cap = _CaptureMcp()
    register_lenie_tools(cap)
    return cap.get("lenie_get_article")
```

Key test cases:
- Found article: assert all 11 response keys present, `source == doc.url`, `content == doc.text`
- `doc.text = None`: `size_kb == 0`, `content is None`
- `doc.reviewed_at = None`: `reviewed_at is None` in response
- Not found (`first()` returns `None`): `pytest.raises(McpError)` with `ARTICLE_NOT_FOUND` code
- `OperationalError` from `session.execute`: `pytest.raises(McpError)` with `DATABASE_UNAVAILABLE` code
- Session closed on success: `session.close.assert_called_once()`
- Session closed on error: `session.close.assert_called_once()`

### No Infrastructure Changes

No changes to:
- `backend/mcp_server/main.py` — `register_lenie_tools(mcp)` already called; new tool registers automatically
- `backend/pyproject.toml` — no new dependencies
- `infra/docker/Dockerfile.mcp` or `compose.nas.yaml`
- `backend/mcp_server/errors.py` — `raise_article_not_found` already implemented

### Project Structure Notes

Files to create/modify:
- **Modified**: `backend/mcp_server/tools/lenie.py` — add `lenie_get_article` inside `register_lenie_tools`
- **Modified**: `backend/mcp_server/tests/unit/test_lenie_tools.py` — add `TestLenieGetArticle` class

No new files required.

### References

- [Epic 36 — Story 36.2 definition](_bmad-output/planning-artifacts/epics/epic-36.md#story-362-lenie_get_article-tool) — Original AC and technical notes
- [Story 36-1 Dev Notes](36-1-lenie-unreviewed-articles-tool.md#dev-notes) — Column mapping discrepancies, session lifecycle, error handling patterns
- [backend/mcp_server/tools/lenie.py](../../backend/mcp_server/tools/lenie.py) — Add `lenie_get_article` here
- [backend/mcp_server/tests/unit/test_lenie_tools.py](../../backend/mcp_server/tests/unit/test_lenie_tools.py) — Add tests here
- [backend/mcp_server/errors.py](../../backend/mcp_server/errors.py) — `raise_article_not_found`, `raise_database_unavailable`
- [backend/library/db/models.py](../../backend/library/db/models.py) — `WebDocument` ORM model (text, url, note, language, reviewed_at, obsidian_note_paths columns)
- [backend/library/db/engine.py](../../backend/library/db/engine.py) — `get_session()` factory

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

None — implementation was straightforward following Dev Notes template from Story 36-1.

### Completion Notes List

- Implemented `lenie_get_article(article_id: int)` inside existing `register_lenie_tools(mcp)` function in `backend/mcp_server/tools/lenie.py` — no new registration function needed.
- Added `raise_article_not_found` to the import from `mcp_server.errors` (already existed in errors.py from Story 35-x).
- Column mapping applied as documented in Dev Notes: `source`←`url`, `content`←`text`, `user_note`←`note`, `added_at`←`created_at.isoformat()`, `size_kb` computed from `len(doc.text.encode()) // 1024`.
- `obsidian_note_paths or []` guard handles legacy records where JSONB column may return `None`.
- 7 unit tests added in class `TestLenieGetArticle`: covers all AC including null text, null reviewed_at, article not found, OperationalError, and session cleanup.
- All 50 MCP unit tests pass (7 new + 43 existing). All 70 backend unit tests pass. Ruff: no errors.

### File List

- `backend/mcp_server/tools/lenie.py` (modified — added `lenie_get_article` tool + `raise_article_not_found` import)
- `backend/mcp_server/tests/unit/test_lenie_tools.py` (modified — added `TestLenieGetArticle` with 9 tests; fixed stale module docstring; removed redundant mock assignment)
- `backend/mcp_server/errors.py` (modified — all `raise_*` helpers changed `-> None` to `-> NoReturn` for correct static analysis)

## Change Log

- 2026-04-15: Implemented story 36-2 — `lenie_get_article` MCP tool with full article retrieval, article-not-found error, database error handling, and 7 unit tests.
- 2026-04-17: Code review fixes — `errors.py`: all `raise_*` functions changed `-> None` → `-> NoReturn`; `test_lenie_tools.py`: 2 new tests (null created_at → added_at=None, null obsidian_note_paths → []), removed redundant mock assignment, updated stale module docstring. 52 MCP tests pass.
- 2026-04-19: Low-severity fixes — `lenie.py`: added `Raises:` section to `lenie_get_article` docstring; `epic-36.md`: corrected `text_content` → `doc.text` (the `text` column) in Story 36.2 technical notes.
