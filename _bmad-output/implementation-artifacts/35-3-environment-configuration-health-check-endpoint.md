# Story 35.3: Environment Configuration & Health Check Endpoint

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **developer**,
I want the MCP server to load configuration from environment variables and expose a `/healthz` endpoint,
so that the container can be monitored by Docker healthchecks and deployment can be verified.

## Acceptance Criteria

1. **AC-1: `backend/mcp_server/config.py` created** — File exists and loads all env vars via `unified_config_loader` (`load_config()`). On startup, if any required var is missing, the server logs a descriptive error and raises `SystemExit(1)`.

   Required vars:
   - `POSTGRESQL_HOST`, `POSTGRESQL_DATABASE`, `POSTGRESQL_USER`, `POSTGRESQL_PASSWORD`, `POSTGRESQL_PORT`
   - `OBSIDIAN_VAULT_PATH` (absolute path to vault on NAS filesystem)

   Optional vars (with defaults):
   - `SECRETS_BACKEND` → default: `"env"`
   - `MCP_SERVER_NAME` → default: `"lenie-mcp"`
   - `LOG_LEVEL` → default: `"INFO"`

2. **AC-2: Config loaded at import time** — `config.py` exposes a module-level `settings` object (or equivalent) so that `main.py` can import it without calling a setup function. Running:
   ```bash
   cd backend && POSTGRESQL_HOST=h POSTGRESQL_DATABASE=d POSTGRESQL_USER=u POSTGRESQL_PASSWORD=p \
     POSTGRESQL_PORT=5432 OBSIDIAN_VAULT_PATH=/tmp \
     PYTHONPATH=. python -c "from mcp_server.config import settings; print(settings.server_name)"
   ```
   prints `lenie-mcp` (or the value of `MCP_SERVER_NAME`).

3. **AC-3: `/healthz` endpoint responds HTTP 200** — Running the server and calling `GET http://localhost:8080/healthz` returns:
   ```json
   {"status": "ok", "server": "lenie-mcp", "version": "0.1.0"}
   ```
   The endpoint is a plain Starlette `Route` mounted in a wrapper `Starlette` app (see Dev Notes). DB is NOT checked — `/healthz` is shallow (connectivity only).

4. **AC-4: Lazy DB connection** — If the database is unavailable at startup, the server still starts and `/healthz` returns HTTP 200. Database errors are deferred to tool invocation time.

5. **AC-5: OBSIDIAN_VAULT_PATH non-existent → WARNING only** — If `OBSIDIAN_VAULT_PATH` points to a non-existent directory, the server logs `WARNING: OBSIDIAN_VAULT_PATH does not exist: <path>` and continues. No crash.

6. **AC-6: LOG_LEVEL respected** — When `LOG_LEVEL=DEBUG`, debug-level log messages appear in output. When `LOG_LEVEL=INFO` (default), debug messages are suppressed. JSON-format logging is used (structured logging for NAS log aggregation).

7. **AC-7: Existing tests pass, ruff clean** — `cd backend && PYTHONPATH=. uvx pytest tests/unit/ -v` passes unchanged. `uvx ruff check backend/` reports no new errors.

## Tasks / Subtasks

- [x] Task 1: Create `backend/mcp_server/config.py` (AC: 1, 2, 5, 6)
  - [x] 1.1 Import `load_config` from `library.config_loader` (backward-compat re-export of `unified_config_loader`)
  - [x] 1.2 Define `McpSettings` dataclass or plain class with all 8 fields (5 required DB + OBSIDIAN_VAULT_PATH + 3 optional with defaults)
  - [x] 1.3 Call `load_config()` to get config dict; extract fields, raise `SystemExit(1)` on missing required vars
  - [x] 1.4 Check `OBSIDIAN_VAULT_PATH` existence with `Path.exists()` → log WARNING if missing (do NOT raise)
  - [x] 1.5 Configure `logging.basicConfig(level=LOG_LEVEL, format=...)` — JSON-compatible format
  - [x] 1.6 Expose module-level `settings = McpSettings(...)` instance

- [x] Task 2: Modify `backend/mcp_server/main.py` to add `/healthz` (AC: 3, 4)
  - [x] 2.1 Import `settings` from `mcp_server.config`
  - [x] 2.2 Create async `healthz(request) → JSONResponse` returning `{"status": "ok", "server": settings.server_name, "version": "0.1.0"}`
  - [x] 2.3 Create wrapper `Starlette` app with `Route("/healthz", endpoint=healthz)` and `Mount("/", app=mcp.streamable_http_app())`
  - [x] 2.4 Expose final `app` (Starlette wrapper, not raw MCP ASGI app) — uvicorn entry `mcp_server.main:app` stays unchanged
  - [x] 2.5 Verify `curl http://localhost:8080/healthz` returns `{"status":"ok",...}` with HTTP 200

- [x] Task 3: Add unit test for config loading (AC: 1, 2)
  - [x] 3.1 Create `backend/mcp_server/tests/unit/test_config.py`
  - [x] 3.2 Test: all required vars present → `settings.server_name == "lenie-mcp"`
  - [x] 3.3 Test: missing `POSTGRESQL_HOST` → `SystemExit` raised
  - [x] 3.4 Test: `OBSIDIAN_VAULT_PATH` non-existent → no exception (only warning)
  - [x] 3.5 Mock `load_config` to avoid real env var dependency in tests

- [x] Task 4: Verify healthz smoke test (AC: 3, 4)
  - [x] 4.1 Start server: `cd backend && PYTHONPATH=. SECRETS_BACKEND=env POSTGRESQL_HOST=h POSTGRESQL_DATABASE=d POSTGRESQL_USER=u POSTGRESQL_PASSWORD=p POSTGRESQL_PORT=5432 OBSIDIAN_VAULT_PATH=/tmp uvicorn mcp_server.main:app --host 0.0.0.0 --port 8081`
  - [x] 4.2 `curl -s http://localhost:8081/healthz` → returns `{"status":"ok","server":"lenie-mcp","version":"0.1.0"}` HTTP 200
  - [x] 4.3 Stop server

- [x] Task 5: Run quality gates (AC: 7)
  - [x] 5.1 `cd backend && PYTHONPATH=. uvx pytest tests/unit/ -v` — 70 passed, 27 skipped (existing suite unchanged)
  - [x] 5.1b `cd backend && PYTHONPATH=. .venv/Scripts/python -m pytest mcp_server/tests/unit/ -v` — runs mcp_server tests (requires project venv with `mcp` and `unified_config_loader`; `uvx` uses isolated env and skips these tests via `importorskip`)
  - [x] 5.2 `uvx ruff check backend/mcp_server/` — no errors (pre-existing errors in other files not introduced by this story)

## Dev Notes

### CRITICAL: Architecture Overrides — Use Story 35-1/35-2 Corrections, NOT epic-35.md

> **⚠️ The epic-35.md describes a standalone `mcp_server/` at project root with `lenie_mcp.server:app`. This was CHANGED in Story 35-1. Use the corrected values below.**

| Aspect | Epic 35.3 says (WRONG) | Correct (established in Story 35-1) |
|--------|------------------------|-------------------------------------|
| Health endpoint | `/health` | **`/healthz`** — Docker D12 convention, matches `backend/server.py` |
| Module path | `lenie_mcp.server:app` | **`mcp_server.main:app`** |
| Config module | `src/lenie_mcp/config.py` | **`backend/mcp_server/config.py`** |
| Python version | 3.12 | **3.11** — project-wide standard |
| Project setup | Standalone pyproject.toml | **Shared `backend/pyproject.toml`** |
| Health response key | (not specified) | `"status": "ok"` (lowercase, matches D12 pattern) |

### Adding `/healthz` to a Starlette/FastMCP ASGI App

`mcp.streamable_http_app()` returns a `starlette.applications.Starlette` app. The cleanest way to add `/healthz` is to create a new Starlette wrapper app:

```python
# backend/mcp_server/main.py (final shape after this story)
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.responses import JSONResponse

from mcp_server.config import settings

mcp = FastMCP(
    name=settings.server_name,
    stateless_http=True,
    json_response=True,
)

VERSION = "0.1.0"

async def healthz(request):
    return JSONResponse({"status": "ok", "server": settings.server_name, "version": VERSION})

app = Starlette(routes=[
    Route("/healthz", endpoint=healthz),
    Mount("/", app=mcp.streamable_http_app()),
])
```

**Why Mount "/"**: The MCP protocol uses paths like `/mcp` and `/sse`. Mounting at `"/"` passes all non-`/healthz` requests to the FastMCP ASGI app. The `Route("/healthz", ...)` is checked first (Starlette processes routes in order).

**Do NOT**: modify the uvicorn entry point — `mcp_server.main:app` still works because we expose `app` at module level.

### Config Loader Pattern

The project uses `unified_config_loader` via the backward-compat re-export in `library.config_loader`:

```python
# backend/mcp_server/config.py
import logging
from dataclasses import dataclass
from pathlib import Path

from library.config_loader import load_config

# Config is a dict subclass — .require(key) calls sys.exit(1) if key missing
# This matches the pattern in backend/server.py: cfg = load_config(); cfg.require("KEY")
cfg = load_config()

logger = logging.getLogger(__name__)


@dataclass
class McpSettings:
    postgresql_host: str
    postgresql_database: str
    postgresql_user: str
    postgresql_password: str
    postgresql_port: str
    obsidian_vault_path: str
    secrets_backend: str
    server_name: str
    log_level: str


def _load_settings() -> McpSettings:
    vault_path = cfg.require("OBSIDIAN_VAULT_PATH")
    if not Path(vault_path).exists():
        logger.warning("OBSIDIAN_VAULT_PATH does not exist: %s", vault_path)

    return McpSettings(
        postgresql_host=cfg.require("POSTGRESQL_HOST"),
        postgresql_database=cfg.require("POSTGRESQL_DATABASE"),
        postgresql_user=cfg.require("POSTGRESQL_USER"),
        postgresql_password=cfg.require("POSTGRESQL_PASSWORD"),
        postgresql_port=cfg.require("POSTGRESQL_PORT"),
        obsidian_vault_path=vault_path,
        secrets_backend=cfg.require("SECRETS_BACKEND", "env"),
        server_name=cfg.require("MCP_SERVER_NAME", "lenie-mcp"),
        log_level=cfg.require("LOG_LEVEL", "INFO"),
    )


settings = _load_settings()

# Configure logging after settings are loaded
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": "%(message)s"}',
)
```

**Note**: `Config.require(key)` (from `unified_config_loader`) calls `sys.exit(1)` automatically when a key is missing — matches `server.py` pattern exactly. No manual missing-var check needed. In unit tests, mock `library.config_loader.load_config` to return a fake dict.

### `unified_config_loader` Import Path

Use `from library.config_loader import load_config, MissingVariableError` — this is the backward-compat re-export that works when `PYTHONPATH=/app` (as set in Dockerfile). Do NOT import directly from `unified_config_loader` in mcp_server code — the `library.config_loader` re-export is the project convention.

### Starlette Dependency

`starlette` is already a transitive dependency of `mcp>=1.0` (FastMCP uses Starlette internally). No new dependency needed in `pyproject.toml`. Verify with:
```bash
cd backend && PYTHONPATH=. python -c "import starlette; print(starlette.__version__)"
```

### Testing Strategy for config.py

Since `_load_settings()` runs at import time (module level), tests must patch env vars BEFORE importing the module. Use `importlib.reload()` or structure tests carefully:

```python
# backend/mcp_server/tests/unit/test_config.py
import sys
import pytest
from unittest.mock import patch
from unified_config_loader import Config  # Config is dict subclass with .require()

def _make_cfg(**kwargs) -> Config:
    """Build a Config object (dict subclass) for test use."""
    full = {
        "POSTGRESQL_HOST": "localhost", "POSTGRESQL_DATABASE": "test",
        "POSTGRESQL_USER": "u", "POSTGRESQL_PASSWORD": "p",
        "POSTGRESQL_PORT": "5432", "OBSIDIAN_VAULT_PATH": "/tmp",
    }
    full.update(kwargs)
    return Config(full)

def test_settings_loads_with_all_required():
    fake_cfg = _make_cfg()
    with patch("library.config_loader.load_config", return_value=fake_cfg):
        sys.modules.pop("mcp_server.config", None)
        import mcp_server.config as cfg_module
        assert cfg_module.settings.server_name == "lenie-mcp"

def test_settings_exits_on_missing_required():
    # Config.require() calls sys.exit(1) when key is missing
    fake_cfg = Config({"POSTGRESQL_HOST": "localhost"})  # missing 5 required vars
    with patch("library.config_loader.load_config", return_value=fake_cfg):
        sys.modules.pop("mcp_server.config", None)
        with pytest.raises(SystemExit):
            import mcp_server.config  # noqa: F401

def test_settings_obsidian_path_missing_warns(tmp_path, caplog):
    fake_cfg = _make_cfg(OBSIDIAN_VAULT_PATH="/nonexistent/path")
    with patch("library.config_loader.load_config", return_value=fake_cfg):
        sys.modules.pop("mcp_server.config", None)
        import mcp_server.config  # noqa: F401
        assert "OBSIDIAN_VAULT_PATH does not exist" in caplog.text
```

### Existing `main.py` State (from Story 35-1)

Current `backend/mcp_server/main.py`:
```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    name="lenie-mcp",
    stateless_http=True,
    json_response=True,
)
app = mcp.streamable_http_app()
```

After this story: `main.py` must import `settings` from `mcp_server.config`, pass `settings.server_name` to `FastMCP`, and replace the bare `mcp.streamable_http_app()` with the Starlette wrapper that adds `/healthz`.

### Docker Healthcheck Alignment

`infra/docker/compose.nas.yaml` (from Story 35-2) already has:
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8080/healthz"]
  interval: 30s
  timeout: 5s
  retries: 3
  start_period: 15s
```

After this story, the container should transition from `(unhealthy)` to `(healthy)`. Verify on NAS after deployment:
```bash
docker inspect lenie-mcp-server --format='{{.State.Health.Status}}'
```

### Project Structure Notes

Files to create/modify in this story:
- **New**: `backend/mcp_server/config.py` — env var loading, settings object
- **Modified**: `backend/mcp_server/main.py` — import settings, add healthz route, wrap ASGI app
- **New**: `backend/mcp_server/tests/unit/test_config.py` — unit tests for config loading

No changes to:
- `backend/pyproject.toml` — `starlette` already in via `mcp` transitive dep, no new dep needed
- `infra/docker/Dockerfile.mcp` — no build changes
- `infra/docker/compose.nas.yaml` — healthcheck already set up in 35-2

### References

- [Story 35-1 Dev Notes](35-1-python-project-structure-mcp-sdk-dependencies.md#dev-notes) — Architecture overrides, `streamable_http_app()` discovery
- [Story 35-2 Dev Notes](35-2-dockerfile-docker-compose-integration.md#dev-notes) — `/healthz` endpoint, compose healthcheck, entry point
- [backend/mcp_server/main.py](../../backend/mcp_server/main.py) — Current state (to be modified)
- [backend/library/config_loader.py](../../backend/library/config_loader.py) — `load_config` re-export pattern
- [backend/server.py#L525-L527](../../backend/server.py) — Flask `/healthz` pattern (reference for response format)
- [Architecture D12](../../_bmad-output/planning-artifacts/architecture.md) — `/healthz` as health endpoint convention
- [Architecture D4](../../_bmad-output/planning-artifacts/architecture.md) — Path security (relevant for OBSIDIAN_VAULT_PATH validation)

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

None.

### Completion Notes List

- Created `backend/mcp_server/config.py` with `McpSettings` dataclass; uses `library.config_loader.load_config()` (Vault/env/aws agnostic). `cfg.require()` auto-exits on missing vars. OBSIDIAN_VAULT_PATH checked with `Path.exists()` — warning-only if missing.
- Modified `backend/mcp_server/main.py`: added Starlette wrapper app with `Route("/healthz", ...)` + `Mount("/", mcp.streamable_http_app())`. Server name now comes from `settings.server_name`.
- Created `backend/mcp_server/tests/unit/test_config.py` with 6 unit tests (skip guard via `pytest.importorskip("unified_config_loader")` for uvx isolated env). All tests mock `library.config_loader.load_config`.
- Smoke test confirmed: `GET /healthz` → `{"status":"ok","server":"lenie-mcp","version":"0.1.0"}` HTTP 200.
- Note: When running locally, `SECRETS_BACKEND=env` must be set explicitly because `.env` at project root sets `SECRETS_BACKEND=vault`. In Docker, `mcp_server.env` already sets `SECRETS_BACKEND=env`.
- Existing 70 unit tests pass; `uvx ruff check backend/mcp_server/` clean.

### File List

- `backend/mcp_server/config.py` (new)
- `backend/mcp_server/main.py` (modified)
- `backend/mcp_server/tests/unit/test_config.py` (new)
- `backend/mcp_server/tests/unit/test_main.py` (new) — healthz endpoint unit tests [added in review]
- `backend/pyproject.toml` (modified) — added `mcp_server/tests` to `testpaths`

## Change Log

| Date | Change |
|------|--------|
| 2026-04-15 | Implemented Story 35.3: created `config.py` (McpSettings, load_config), modified `main.py` (healthz route, Starlette wrapper), added unit tests for config loading |
