# Story 35.1: Python Project Structure & MCP SDK Dependencies

Status: done

## Story

As a **developer**,
I want a `backend/mcp_server/` directory skeleton with the MCP SDK added to `backend/pyproject.toml` and Flask independence of existing services verified,
so that subsequent stories can implement MCP tools against a stable, convention-compliant foundation without rebuilding the scaffold.

## Acceptance Criteria

1. **AC-1: Directory structure** — `backend/mcp_server/` exists with the following files (stubs only — no tool logic yet):
   ```
   backend/mcp_server/
   ├── __init__.py           # empty
   ├── main.py               # FastMCP instance + transport config (no tools registered)
   ├── errors.py             # Error enum + McpError helpers (6 codes, stubs)
   ├── path_security.py      # ensure_within_vault() skeleton (raises NotImplementedError)
   ├── tools/
   │   ├── __init__.py       # empty
   │   ├── lenie.py          # empty module with docstring
   │   ├── obsidian.py       # empty module with docstring
   │   └── _common.py        # empty module with docstring
   └── tests/
       ├── unit/             # empty directory with __init__.py
       └── integration/      # empty directory with __init__.py
   ```

2. **AC-2: MCP SDK in pyproject.toml** — `mcp>=1.0` (or latest stable) is added to `backend/pyproject.toml` under `[project.dependencies]`. `uv lock` runs cleanly, `uv.lock` is updated.

3. **AC-3: FastMCP instance in main.py** — `main.py` contains a working `FastMCP` instance named `"lenie-mcp"`, configured for streamable HTTP transport:
   ```python
   from mcp.server.fastmcp import FastMCP
   mcp = FastMCP("lenie-mcp", stateless_http=True, json_response=True)
   app = mcp.get_asgi_app()  # or equivalent for streamable-http
   ```
   Running `cd backend && PYTHONPATH=. python -c "from mcp_server.main import mcp; print(mcp.name)"` prints `lenie-mcp` without errors.

4. **AC-4: Error enum skeleton in errors.py** — `errors.py` defines `McpErrorCode` enum and 6 helper functions that raise `McpError` (from `mcp` SDK) with JSON-RPC codes in `-32000..-32099` range:
   ```python
   from enum import IntEnum
   from mcp import McpError   # or mcp.types.McpError — verify correct import
   
   class McpErrorCode(IntEnum):
       ARTICLE_NOT_FOUND = -32001
       NOTE_NOT_FOUND = -32002
       NOTE_PATH_INVALID = -32003
       VAULT_WRITE_FAILED = -32004
       DATABASE_UNAVAILABLE = -32005
       VERSION_SAVE_FAILED = -32006
   
   def raise_article_not_found(article_id: int) -> None: ...
   def raise_note_not_found(path: str) -> None: ...
   def raise_note_path_invalid(path: str) -> None: ...
   def raise_vault_write_failed(detail: str = "") -> None: ...
   def raise_database_unavailable() -> None: ...
   def raise_version_save_failed() -> None: ...
   ```
   Each helper must include the Polish user-facing message from the PRD error contract (e.g. `"Nie znalazłem artykułu o tym ID — możliwe że został wcześniej usunięty."`).

5. **AC-5: Path security skeleton in path_security.py** — `path_security.py` defines `ensure_within_vault(relative_path: str, vault_root: Path) -> Path`. In this story it may raise `NotImplementedError` — full implementation is deferred to the Obsidian tools story. The function signature and docstring must be correct:
   ```python
   from pathlib import Path
   
   def ensure_within_vault(relative_path: str, vault_root: Path) -> Path:
       """Resolve relative_path and verify it stays within vault_root/02-wiedza/.
       Raises raise_note_path_invalid() if path escapes the allowed area.
       Uses Path.resolve(strict=False) + is_relative_to() per architecture D4.
       """
       raise NotImplementedError("Implemented in Epic 38")
   ```

6. **AC-6: Flask independence verified (D8)** — Running the import below from a Python interpreter WITHOUT an active Flask app context (no `flask` application context on stack) succeeds without error:
   ```python
   cd backend && PYTHONPATH=. python -c "
   from library.services.document_service import DocumentService
   from library.services.search_service import SearchService
   print('Flask independence: OK')
   "
   ```
   If import fails due to `current_app`, `request`, or other Flask globals being accessed at import time → **STOP**: open a separate issue and block this story until resolved. Document the coupling in Dev Notes.

7. **AC-7: .venv_wsl synchronized** — After adding `mcp` to `pyproject.toml`, `.venv_wsl` is synced per CLAUDE.md convention:
   ```bash
   wsl bash -c "export PATH=\"\$HOME/.local/bin:\$PATH\" && cd /mnt/c/Users/ziutus/git/_lenie-all/lenie-server-2025/backend && uv pip install -e ../shared_python/unified-config-loader/ --python .venv_wsl/bin/python"
   ```

8. **AC-8: Existing tests pass** — `cd backend && PYTHONPATH=. uvx pytest tests/unit/ -v` passes with the same result as before (no regressions from `uv add mcp`). Ruff clean: `uvx ruff check backend/`.

## Tasks / Subtasks

- [x] Task 1: Add `mcp` SDK to backend dependencies (AC: 2, 3)
  - [x] 1.1 Run `cd backend && uv add mcp` — adds to `pyproject.toml` + updates `uv.lock`
  - [x] 1.2 Verify import: `cd backend && PYTHONPATH=. python -c "from mcp.server.fastmcp import FastMCP; print('OK')"`
  - [x] 1.3 Sync `.venv_wsl` (AC-7)

- [x] Task 2: Create directory skeleton (AC: 1)
  - [x] 2.1 `mkdir -p backend/mcp_server/tools backend/mcp_server/tests/unit backend/mcp_server/tests/integration`
  - [x] 2.2 Create `backend/mcp_server/__init__.py` (empty)
  - [x] 2.3 Create `backend/mcp_server/tools/__init__.py`, `tools/lenie.py`, `tools/obsidian.py`, `tools/_common.py` (empty modules with docstrings)
  - [x] 2.4 Create `backend/mcp_server/tests/unit/__init__.py` and `tests/integration/__init__.py` (empty)

- [x] Task 3: Create main.py with FastMCP skeleton (AC: 3)
  - [x] 3.1 Create `backend/mcp_server/main.py` with FastMCP instance configured for `streamable-http` transport
  - [x] 3.2 Add `app = mcp.streamable_http_app()` (equivalent to `get_asgi_app()`) for Docker entry point
  - [x] 3.3 Verify: `cd backend && PYTHONPATH=. python -c "from mcp_server.main import mcp; print(mcp.name)"`

- [x] Task 4: Create errors.py skeleton (AC: 4)
  - [x] 4.1 Create `backend/mcp_server/errors.py` with `McpErrorCode` IntEnum and 6 helper functions
  - [x] 4.2 Include all Polish user-facing messages from PRD error contract verbatim
  - [x] 4.3 Verify correct import path for `McpError` from `mcp` SDK (check SDK source/docs)

- [x] Task 5: Create path_security.py skeleton (AC: 5)
  - [x] 5.1 Create `backend/mcp_server/path_security.py` with function signature + docstring

- [x] Task 6: Verify Flask independence (AC: 6)
  - [x] 6.1 Run import test for `DocumentService` and `SearchService` outside Flask context
  - [x] 6.2 If coupling found: document in Dev Notes, open blocking issue, do NOT proceed to Epic 36

- [x] Task 7: Quality checks (AC: 8)
  - [x] 7.1 `cd backend && PYTHONPATH=. uvx pytest tests/unit/ -v` — all pass
  - [x] 7.2 `uvx ruff check backend/mcp_server/` — no new issues (pre-existing backend issues excluded)

## Dev Notes

### Architecture Overrides — Epic vs Architecture Document

> **⚠️ CRITICAL: The epic-35.md description has errors. Architecture document takes precedence.**

| Aspect | Epic says (WRONG) | Architecture says (CORRECT) |
|--------|-------------------|------------------------------|
| Location | `mcp_server/` at project root | `backend/mcp_server/` inside backend/ |
| Python | 3.12 | 3.11 (project-wide standard) |
| Setup | Standalone `pyproject.toml` + `uv sync` | `uv add mcp` into existing `backend/pyproject.toml` |
| Entry point | `server.py` | `main.py` |
| Health path | `/health` | `/healthz` (matches backend convention) |

### Project Structure Notes

**MCP server lives inside `backend/`** — it shares:
- `backend/pyproject.toml` (same uv project, same `mcp` dependency as everything else)
- `backend/library/` services (imported directly by tools)
- `backend/tests/` pattern (`cd backend && PYTHONPATH=. uvx pytest ...`)
- `backend/alembic/` for migrations (used in Epic 38 Story 38-1)

**Dockerfile** (Story 35-2, next story) will be a NEW file at `infra/docker/Dockerfile.mcp` or added as a separate build stage — NOT the existing `backend/Dockerfile` (which builds Flask server.py only).

### FastMCP Transport Configuration

From architecture D3 + SDK docs:
```python
# backend/mcp_server/main.py
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    name="lenie-mcp",
    stateless_http=True,   # Production mode — no session state
    json_response=True,    # JSON-RPC wire format
)
# The ASGI app is exposed for uvicorn to serve
app = mcp.get_asgi_app()
```

Run command (used in Docker later):
```bash
cd backend && PYTHONPATH=. uvicorn mcp_server.main:app --host 0.0.0.0 --port 8080
```
Or alternatively: `mcp.run(transport="streamable-http")` (check SDK docs for which is preferred).

### Error Code Mapping (D6 — errors.py)

All 6 PRD error codes must map to JSON-RPC range `-32000..-32099`:

| Error Code | JSON-RPC | Polish message (from PRD — copy verbatim) |
|------------|----------|--------------------------------------------|
| `article_not_found` | -32001 | `"Nie znalazłem artykułu o tym ID — możliwe że został wcześniej usunięty."` |
| `note_not_found` | -32002 | `"Nie ma notatki pod tą ścieżką w 02-wiedza/."` |
| `note_path_invalid` | -32003 | `"Ścieżka jest poza dozwolonym obszarem 02-wiedza/."` |
| `vault_write_failed` | -32004 | `"Nie udało się zapisać notatki — sprawdź miejsce na dysku i status Obsidian Sync."` |
| `database_unavailable` | -32005 | `"Baza Lenie jest niedostępna — sprawdź czy NAS i kontener lenie-ai-db działają."` |
| `version_save_failed` | -32006 | `"Wstrzymałem zapis notatki — nie mogłem zapisać wersji historycznej. Notatka nie została zmieniona."` |

Verify the correct import: `from mcp import McpError` or `from mcp.types import McpError` — check SDK 1.x source at `modelcontextprotocol/python-sdk`.

### Flask Independence Verification (D8)

`DocumentService` is in `backend/library/services/document_service.py` and `SearchService` is in `backend/library/services/search_service.py` (post-Epic 32). The verification in AC-6 must pass. If it fails, common culprits:
- `from flask import current_app` at module top level
- `flask_sqlalchemy.SQLAlchemy` vs standalone `sqlalchemy` engine

If coupling found: MCP tools must NOT import services directly — an adapter layer is needed. Block story, document exact error, open new backlog item.

### Error Messages — PRD Verbatim Policy

AC-4 requires messages "verbatim from the PRD error contract." Helpers follow this with one intentional extension: `raise_article_not_found` and `raise_note_not_found` append machine-readable context `(id=..., path=...)` after the Polish sentence. The PRD text is always present and unmodified at the start of the message. This extension is intentional for debuggability and is documented in the `errors.py` module docstring.

### `mcp_server/tests/__init__.py` — Extra File vs AC-1

AC-1 defines `tests/unit/__init__.py` and `tests/integration/__init__.py` but does not list `tests/__init__.py` (parent level). The extra file was added intentionally to make `mcp_server/tests/` a proper Python package, which simplifies pytest collection. It is tracked in the File List.

### `__pycache__` Directories

`backend/mcp_server/__pycache__/` appears in `git status` as untracked but is excluded from commits by `.gitignore` (`__pycache__/` rule). No action required. Note: `.pyc` files reflect the Python version used during development (may differ from 3.11). Always run MCP verification commands via `.venv/Scripts/python` (Python 3.11) — not system Python.

### Path Security (D4) — What's Deferred

`path_security.py` in this story is a STUB only. Full implementation (using `pathlib.Path.resolve(strict=False)` + `.is_relative_to()`) comes in Epic 38 Story 38-2 (obsidian_read_note + obsidian_list_notes). The stub must have the correct signature so imports don't fail.

### Testing Standard

- **Standard backend tests**: `cd backend && PYTHONPATH=. uvx pytest tests/unit/ -v`
  - Uses `uvx` (isolated env) — does NOT include `mcp` package, so MCP tests are skipped via `pytest.importorskip`
- **MCP server tests** (require `mcp` installed in venv): `cd backend && PYTHONPATH=. .venv/Scripts/python -m pytest mcp_server/tests/unit/ -v`
  - Must use `.venv/Scripts/python` (Python 3.11) — do NOT use system Python (may be 3.12/3.13)
- `testpaths` in `pyproject.toml` includes `["tests", "mcp_server/tests"]` — both suites discovered when running `pytest` without path args via venv
- No test file needed for `main.py` skeleton in this story

### .venv_wsl Requirement

After `uv add mcp` changes `pyproject.toml`, the `.venv_wsl` must be synced (per CLAUDE.md):
```bash
wsl bash -c "export PATH=\"\$HOME/.local/bin:\$PATH\" && cd /mnt/c/Users/ziutus/git/_lenie-all/lenie-server-2025/backend && uv pip install -e ../shared_python/unified-config-loader/ --python .venv_wsl/bin/python"
```

### References

- [Architecture: Sprint 10 MCP Server section](../_bmad-output/planning-artifacts/architecture.md#sprint-10--core-architectural-decisions) — D1–D12 decisions
- [Architecture: Project Structure](../_bmad-output/planning-artifacts/architecture.md#project-structure-within-backend) — `backend/mcp_server/` canonical layout
- [PRD: Error Handling](../_bmad-output/planning-artifacts/prd.md#error-handling) — 6 error codes with Polish messages
- [PRD: Implementation Considerations](../_bmad-output/planning-artifacts/prd.md#implementation-considerations) — transport and SDK choice
- [backend/library/services/document_service.py](../../backend/library/services/document_service.py) — service to verify (AC-6)
- [backend/library/services/search_service.py](../../backend/library/services/search_service.py) — service to verify (AC-6)

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- AC-6 Flask independence: `library.document_service` and `library.search_service` are at `backend/library/` (not `library/services/` as stated in Dev Notes). Import verified with `.venv/Scripts/python` — passes cleanly with no Flask context.
- Task 3.2: `mcp.get_asgi_app()` does not exist in mcp==1.27.0; `mcp.streamable_http_app()` is the correct equivalent (returns `starlette.applications.Starlette`).
- `uvx pytest` uses an isolated env without `mcp` installed; tests for mcp_server must be run with `.venv/Scripts/python -m pytest`.

### Completion Notes List

- Added `mcp==1.27.0` to `backend/pyproject.toml` via `uv add mcp`; `uv.lock` updated. `.venv_wsl` synced.
- Created `backend/mcp_server/` skeleton: `__init__.py`, `main.py`, `errors.py`, `path_security.py`, `tools/` (4 files), `tests/unit/`, `tests/integration/`.
- `main.py`: FastMCP instance `"lenie-mcp"` with `stateless_http=True, json_response=True`, ASGI app via `mcp.streamable_http_app()`. Verified: `from mcp_server.main import mcp; print(mcp.name)` → `lenie-mcp`.
- `errors.py`: `McpErrorCode` IntEnum (6 codes, -32001..-32006), 6 raise helpers with Polish PRD messages verbatim. Import: `from mcp import McpError` (confirmed correct for mcp 1.27.0).
- `path_security.py`: `ensure_within_vault()` stub with correct signature and docstring; raises `NotImplementedError` (full impl in Epic 38).
- Flask independence: `DocumentService` and `SearchService` import cleanly outside Flask context — no coupling found.
- 23 unit tests for `errors.py` added (`mcp_server/tests/unit/test_errors.py`) — all pass.
- Existing 70 unit tests pass, 27 skipped — zero regressions.
- Ruff clean on `backend/mcp_server/`.
- **[Code Review Fix]** Added `pytest.importorskip("mcp")` to `test_errors.py` — MCP tests now gracefully skip in `uvx` isolated env (no `mcp` package), run fully with `.venv/Scripts/python -m pytest`.
- **[Code Review Fix]** Updated `pyproject.toml` `testpaths` to `["tests", "mcp_server/tests"]` — MCP tests now discoverable when running `pytest` without path arguments via venv Python.
- **[Code Review Fix]** Updated Testing Standard in Dev Notes to document the two-runner model (uvx for backend, venv Python 3.11 for MCP tests).

### File List

- `backend/pyproject.toml` — added `mcp>=1.0` dependency
- `backend/uv.lock` — updated with mcp==1.27.0 and transitive deps
- `backend/mcp_server/__init__.py` — empty package init
- `backend/mcp_server/main.py` — FastMCP instance + ASGI app
- `backend/mcp_server/errors.py` — McpErrorCode enum + 6 raise helpers
- `backend/mcp_server/path_security.py` — ensure_within_vault() stub
- `backend/mcp_server/tools/__init__.py` — empty
- `backend/mcp_server/tools/lenie.py` — empty module with docstring
- `backend/mcp_server/tools/obsidian.py` — empty module with docstring
- `backend/mcp_server/tools/_common.py` — empty module with docstring
- `backend/mcp_server/tests/__init__.py` — empty
- `backend/mcp_server/tests/unit/__init__.py` — empty
- `backend/mcp_server/tests/integration/__init__.py` — empty
- `backend/mcp_server/tests/unit/test_errors.py` — 23 unit tests for errors.py

## Change Log

- 2026-04-15: Story 35-1 implemented — MCP server scaffold created, mcp==1.27.0 added, Flask independence verified, 23 tests added.
- 2026-04-15: Code review fixes (Medium) — `pytest.importorskip("mcp")` added to test file; `testpaths` updated; Testing Standard documented.
- 2026-04-15: Code review fixes (Low) — `mcp<2.0` upper bound added; errors.py docstring clarifies verbatim policy; Dev Notes document `tests/__init__.py` and `__pycache__` intent.
