# Story 36.1: lenie_unreviewed_articles Tool

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **user on mobile**,
I want to ask Claude to show me my unreviewed articles,
so that I can decide which one to read and process during a short mobile session.

## Acceptance Criteria

1. **AC-1: Tool registered in FastMCP** — `lenie_unreviewed_articles` is registered as an MCP tool in `backend/mcp_server/tools/lenie.py` and imported in `backend/mcp_server/main.py`. Running the server and listing tools via MCP client reveals `lenie_unreviewed_articles`.

2. **AC-2: Default invocation returns up to 6 articles** — When invoked with no parameters, the tool returns a list of at most 6 articles where `reviewed_at IS NULL OR obsidian_note_paths = '[]'`, ordered by `created_at DESC`. Each item contains:
   - `id` (integer)
   - `title` (string or `null`)
   - `source` (URL string — the `url` column)
   - `size_kb` (integer — `len(text.encode()) // 1024` if `text` is set, else `0`)
   - `user_note` (string or `null` — the `note` column)
   - `added_at` (ISO 8601 date string — from `created_at` column)
   - `total_unreviewed` (integer — total count with same filter, no OFFSET)

3. **AC-3: `limit` parameter respected** — When invoked with `limit=3`, at most 3 articles are returned.

4. **AC-4: `source_filter` parameter** — When invoked with `source_filter="bbc.com"`, only articles whose `url` contains `bbc.com` (case-insensitive ILIKE) are returned.

5. **AC-5: `type_filter` parameter** — When invoked with `type_filter="webpage"` (or `"youtube"`, `"link"`), only articles with matching `document_type` are returned.

6. **AC-6: `offset` parameter** — When invoked with `offset=6`, articles 7–12 are returned (using SQL `OFFSET 6`).

7. **AC-7: Database unavailable → error** — When PostgreSQL is unavailable, the tool raises `McpError` via `raise_database_unavailable()` from `mcp_server.errors`.

8. **AC-8: Empty result** — When there are no unreviewed articles, the tool returns an empty list with `total_unreviewed: 0` (not an error).

9. **AC-9: Performance** — Response within 2 seconds for default limit of 6.

10. **AC-10: Quality gates pass** — `cd backend && PYTHONPATH=. uvx pytest tests/unit/ -v` passes unchanged. `uvx ruff check backend/mcp_server/` reports no new errors.

## Tasks / Subtasks

- [x] Task 1: Implement `lenie_unreviewed_articles` in `backend/mcp_server/tools/lenie.py` (AC: 1–9)
  - [x] 1.1 Add direct SQLAlchemy ORM query using `WebDocument` model and `get_session()` from `library.db.engine`
  - [x] 1.2 Filter: `WHERE (reviewed_at IS NULL OR obsidian_note_paths = '[]') ORDER BY created_at DESC LIMIT :limit OFFSET :offset`
  - [x] 1.3 Add `source_filter` support: `url.ilike(f"%{source_filter}%")` (AC: 4)
  - [x] 1.4 Add `type_filter` support: `document_type == type_filter` (AC: 5)
  - [x] 1.5 Run separate `COUNT(*)` query with same filter (no OFFSET) for `total_unreviewed` (AC: 2)
  - [x] 1.6 Map columns to response dict: `id`, `title`, `source`←`url`, `size_kb`, `user_note`←`note`, `added_at`←`created_at.isoformat()`
  - [x] 1.7 Wrap DB calls in try/except `OperationalError` → `raise_database_unavailable()` (AC: 7)

- [x] Task 2: Register tool in `backend/mcp_server/main.py` (AC: 1)
  - [x] 2.1 Import `lenie_unreviewed_articles` from `mcp_server.tools.lenie` after tool registration

- [x] Task 3: Add unit tests in `backend/mcp_server/tests/unit/test_lenie_tools.py` (AC: 2–8)
  - [x] 3.1 Test: default invocation returns ≤6 items with correct keys (mock session)
  - [x] 3.2 Test: `limit=3` returns at most 3 items
  - [x] 3.3 Test: `source_filter` filters by `url` ILIKE
  - [x] 3.4 Test: `type_filter` filters by `document_type`
  - [x] 3.5 Test: `OperationalError` → `McpError` with `DATABASE_UNAVAILABLE` code
  - [x] 3.6 Test: empty result → empty list + `total_unreviewed: 0`

- [x] Task 4: Run quality gates (AC: 10)
  - [x] 4.1 `cd backend && PYTHONPATH=. uvx pytest tests/unit/ -v` — existing suite passes
  - [x] 4.2 `cd backend && PYTHONPATH=. .venv/Scripts/python -m pytest mcp_server/tests/unit/ -v` — new tests pass
  - [x] 4.3 `uvx ruff check backend/mcp_server/` — no new errors

## Dev Notes

### CRITICAL: Architecture Override — Use `library.db.engine`, NOT `lenie_mcp.db`

> **⚠️ Epic-36.md mentions `get_session()` from `lenie_mcp.db`. This module does NOT exist. Use the established pattern from Stories 35-1 through 35-3.**

| Aspect | Epic 36 says (WRONG) | Correct (established in Stories 35-x) |
|--------|----------------------|---------------------------------------|
| Session factory | `from lenie_mcp.db import get_session` | `from library.db.engine import get_session` |
| Module path | `lenie_mcp.server:app` | `mcp_server.main:app` |
| Config | standalone pyproject | `backend/pyproject.toml` (shared) |

### CRITICAL: Column Name Mapping — Epic vs ORM

Epic-36.md uses names that differ from the actual `WebDocument` ORM columns in `library/db/models.py`:

| Epic field | ORM column | Notes |
|------------|-----------|-------|
| `content` | `text` | `text_content` does NOT exist in DB/ORM |
| `source` (URL) | `url` | `source` column = discovery channel ("own", "unknow.news") — NOT the article URL |
| `user_note` | `note` | Direct column access: `doc.note` |
| `added_at` | `created_at` | DateTime, use `.isoformat()` |
| `size_kb` | computed | `len(doc.text.encode()) // 1024 if doc.text else 0` |

> **`source_filter` filters the `url` column (article URL), not the `source` column (discovery channel).**
> The parameter name in the AC says "articles whose `source` URL contains `bbc.com`" — this means the article's URL, not the `source` discovery field.

### Tool Implementation Pattern (FastMCP)

Register tools using `@mcp.tool()` decorator. The `mcp` instance lives in `mcp_server.main`. Tools in `tools/lenie.py` must receive the `mcp` instance at import time — use a registration function pattern (consistent with how `tools/obsidian.py` will be structured):

```python
# backend/mcp_server/tools/lenie.py
"""Lenie MCP tools — article retrieval, search, and management tools for the Lenie knowledge base."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy.exc import OperationalError
from sqlalchemy import func, or_, cast, Text

from library.db.engine import get_session
from library.db.models import WebDocument
from mcp_server.errors import raise_database_unavailable

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)


def register_lenie_tools(mcp: "FastMCP") -> None:
    """Register all Lenie knowledge-base tools with the MCP server."""

    @mcp.tool()
    def lenie_unreviewed_articles(
        limit: int = 6,
        offset: int = 0,
        source_filter: str | None = None,
        type_filter: str | None = None,
    ) -> dict:
        """Return a list of unreviewed articles from the Lenie knowledge base.

        Articles are unreviewed when reviewed_at IS NULL or obsidian_note_paths is empty ([]).
        Results are ordered newest-first (created_at DESC).
        """
        session = get_session()
        try:
            # Base filter: unreviewed
            unreviewed_filter = or_(
                WebDocument.reviewed_at.is_(None),
                cast(WebDocument.obsidian_note_paths, Text) == "[]",
            )
            stmt = (
                select(WebDocument)
                .where(unreviewed_filter)
            )
            count_stmt = (
                select(func.count(WebDocument.id))
                .where(unreviewed_filter)
            )

            if source_filter:
                url_filter = WebDocument.url.ilike(f"%{source_filter}%")
                stmt = stmt.where(url_filter)
                count_stmt = count_stmt.where(url_filter)

            if type_filter:
                type_f = WebDocument.document_type == type_filter
                stmt = stmt.where(type_f)
                count_stmt = count_stmt.where(type_f)

            total_unreviewed = session.execute(count_stmt).scalar() or 0

            stmt = stmt.order_by(WebDocument.created_at.desc()).limit(limit).offset(offset)
            docs = session.execute(stmt).scalars().all()

            articles = []
            for doc in docs:
                size_kb = len(doc.text.encode()) // 1024 if doc.text else 0
                articles.append({
                    "id": doc.id,
                    "title": doc.title,
                    "source": doc.url,
                    "size_kb": size_kb,
                    "user_note": doc.note,
                    "added_at": doc.created_at.isoformat() if doc.created_at else None,
                    "total_unreviewed": total_unreviewed,
                })

            return {"articles": articles, "total_unreviewed": total_unreviewed}
        except OperationalError:
            raise_database_unavailable()
        finally:
            session.close()
```

**Note on `total_unreviewed` placement**: The field appears in each article item per the AC, but also returned at the top level for convenience when the list is empty.

### Register in main.py

```python
# backend/mcp_server/main.py (add after existing imports)
from mcp_server.tools.lenie import register_lenie_tools

# After mcp = FastMCP(...) instantiation:
register_lenie_tools(mcp)
```

### ORM Import for `select`

`select` is from `sqlalchemy` — not re-exported from `library.*`. Direct import:

```python
from sqlalchemy import func, or_, cast, Text, select
```

### JSONB Empty Array Filter

The `obsidian_note_paths` column is `JSONB` (`Mapped[list]`). Comparing with `== []` in SQLAlchemy ORM generates `obsidian_note_paths = '[]'::jsonb`, which matches the epic's SQL. Alternatively, use `cast(WebDocument.obsidian_note_paths, Text) == "[]"` for explicit text comparison. Either approach works — prefer `cast` for clarity.

### Session Lifecycle in MCP Tools

FastMCP tools are synchronous functions. Use a plain `get_session()` (returns a new `Session`), execute the query, close the session in a `finally` block. Do **not** use `get_scoped_session()` (that's for Flask thread-local sessions).

### Error Handling

All database errors go through `raise_database_unavailable()` from `mcp_server.errors` — already implemented in Story 35-1. Catch `sqlalchemy.exc.OperationalError` for connection issues.

### Testing Strategy

The `mcp_server/tests/unit/` tests use `pytest.importorskip("unified_config_loader")` to skip under uvx isolated env (which doesn't have the project venv). For the new `test_lenie_tools.py`, mock the session:

```python
pytest_mock or unittest.mock.MagicMock
```

Mock `library.db.engine.get_session` to return a mock session. Do NOT use real DB in unit tests.

### Performance Note

The query uses `ORDER BY created_at DESC LIMIT 6 OFFSET 0` with the `obsidian_note_paths = '[]'` JSONB cast. For the NAS with ~thousands of articles, this should be well within the 2-second NFR. If needed, add a partial index — but not required for MVP.

### Project Structure Notes

Files to create/modify in this story:
- **Modified**: `backend/mcp_server/tools/lenie.py` — implement `lenie_unreviewed_articles` via `register_lenie_tools(mcp)`
- **Modified**: `backend/mcp_server/main.py` — call `register_lenie_tools(mcp)` after FastMCP instantiation
- **New**: `backend/mcp_server/tests/unit/test_lenie_tools.py` — unit tests (mocked session)

No changes to:
- `backend/pyproject.toml` — no new dependencies needed (`sqlalchemy` already in base deps)
- `backend/mcp_server/errors.py` — `raise_database_unavailable()` already implemented
- `backend/mcp_server/config.py` — no new config vars needed
- `infra/docker/Dockerfile.mcp` or `compose.nas.yaml` — no infrastructure changes

### References

- [Epic 36 description](_bmad-output/planning-artifacts/epics/epic-36.md#story-361-lenie_unreviewed_articles-tool) — Original AC and technical notes (note column name discrepancies flagged above)
- [Story 35-3 Dev Notes](35-3-environment-configuration-health-check-endpoint.md#dev-notes) — Architecture overrides, `mcp_server.main:app` pattern
- [backend/mcp_server/main.py](../../backend/mcp_server/main.py) — Current state (add `register_lenie_tools` import and call)
- [backend/mcp_server/tools/lenie.py](../../backend/mcp_server/tools/lenie.py) — Stub to implement
- [backend/mcp_server/errors.py](../../backend/mcp_server/errors.py) — `raise_database_unavailable()` helper
- [backend/library/db/models.py](../../backend/library/db/models.py) — `WebDocument` ORM model (reviewed_at, obsidian_note_paths, note, url, text columns)
- [backend/library/db/engine.py](../../backend/library/db/engine.py) — `get_session()` factory
- [backend/library/stalker_web_documents_db_postgresql.py](../../backend/library/stalker_web_documents_db_postgresql.py) — `WebsitesDBPostgreSQL` (reference for ORM query patterns)

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

None — implementation was straightforward following the Dev Notes template.

### Completion Notes List

- Implemented `register_lenie_tools(mcp)` pattern in `backend/mcp_server/tools/lenie.py` using `@mcp.tool()` decorator inside the registration function, consistent with FastMCP patterns described in Dev Notes.
- Used `cast(WebDocument.obsidian_note_paths, Text) == "[]"` for explicit JSONB empty-array comparison (as recommended in Dev Notes over `== []`).
- Separate `COUNT(*)` query runs with the same filters but without OFFSET/LIMIT — `total_unreviewed` appears both in each article dict (per AC-2) and at the top-level return dict (for empty list case per AC-8).
- 11 unit tests added covering: correct keys, default limit=6, custom limit, source_filter, type_filter, OperationalError → McpError, empty result, session.close() on success and error, null text/created_at edge cases.
- All 70 existing backend unit tests pass (0 regressions). All 42 MCP unit tests pass. Ruff reports no errors.

### File List

- `backend/mcp_server/tools/lenie.py` (modified — implemented `register_lenie_tools` with `lenie_unreviewed_articles` tool)
- `backend/mcp_server/main.py` (modified — added `register_lenie_tools` import and call)
- `backend/mcp_server/tests/unit/test_lenie_tools.py` (new — 11 unit tests with mocked session)

## Change Log

- 2026-04-15: Implemented story 36-1 — `lenie_unreviewed_articles` MCP tool with filtering, pagination, error handling, and 11 unit tests.
- 2026-04-15: Code review fixes applied — (1) added missing `offset` unit test (AC-6 coverage); (2) improved filter tests to assert SQL WHERE clause via `call_args_list`; (3) moved `session = get_session()` inside try block with `if session is not None` guard in finally; (4) fixed typo `TestLeniUnreviewedArticles` → `TestLenieUnreviewedArticles`. Tests: 12 passed (was 11).
