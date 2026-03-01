# Story 21.1: Project Scaffolding & Slack Connection

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **developer**,
I want a `slack_bot/` project with Docker container that connects to Slack via Socket Mode,
So that I have a running bot foundation to build commands on.

## Acceptance Criteria

1. **Given** Docker Compose file has a `slack` profile with the bot service
   **When** developer runs `docker compose --profile slack up -d`
   **Then** the bot container starts and connects to Slack via Socket Mode within 10 seconds

2. **Given** the bot successfully connects to Slack
   **When** connection is established
   **Then** bot posts a startup confirmation message to a designated channel with version info

3. **Given** Slack tokens are stored in Vault (or SSM/env)
   **When** the bot starts
   **Then** it retrieves `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, and `STALKER_API_KEY` from the configured secret backend

4. **Given** the bot is running
   **When** inspecting source code and Docker image
   **Then** zero secrets are hardcoded and logs never contain token values

**Covers:** FR21, FR22, FR24 | NFR2, NFR4-NFR7, NFR10-NFR11, NFR14-NFR15

## Tasks / Subtasks

- [x] Task 1: Create `slack_bot/` directory structure (AC: #1, #3, #4)
  - [x] 1.1: Create `slack_bot/src/__init__.py` with `__version__ = "0.1.0"`
  - [x] 1.2: Create `slack_bot/src/config.py` — self-contained config loader (env/vault/aws)
  - [x] 1.3: Create `slack_bot/src/main.py` — entry point with Socket Mode connection
  - [x] 1.4: Create `slack_bot/tests/__init__.py` and `slack_bot/tests/unit/__init__.py`
- [x] Task 2: Create `slack_bot/pyproject.toml` with pinned dependencies (AC: #1)
  - [x] 2.1: Pin `slack-bolt>=1.27.0,<2.0.0` and `slack-sdk>=3.40.0,<4.0.0`
  - [x] 2.2: Add `python-json-logger>=3.0,<4.0` (v4 has breaking API changes — avoid)
  - [x] 2.3: Add `python-dotenv>=1.0.0` and `hvac>=2.1.0` (optional extra for vault)
  - [x] 2.4: Add dev dependencies: `pytest`, `ruff`
  - [x] 2.5: Configure ruff: `line-length = 120` (consistent with backend)
- [x] Task 3: Implement `config.py` — self-contained config module (AC: #3, #4)
  - [x] 3.1: Port config_loader pattern from `backend/library/config_loader.py`: `Config` dict subclass with `require()` method
  - [x] 3.2: Implement `EnvBackend` (python-dotenv + os.environ)
  - [x] 3.3: Implement `VaultBackend` (hvac KV v2, path: `secret/{PROJECT_CODE}/{SECRETS_ENV}`)
  - [x] 3.4: Implement `AWSSSMBackend` (boto3 GetParametersByPath under `/{PROJECT_CODE}/{SECRETS_ENV}/`)
  - [x] 3.5: Implement `load_config()` factory with `SECRETS_BACKEND` env var, module-level singleton
  - [x] 3.6: Define required vars: `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, `LENIE_API_URL`, `STALKER_API_KEY`
  - [x] 3.7: Ensure no secrets logged — never log token values, even at DEBUG
- [x] Task 4: Implement `main.py` — Socket Mode entry point (AC: #1, #2)
  - [x] 4.1: Initialize Slack Bolt `App` with bot token from config
  - [x] 4.2: Create `SocketModeHandler` with app-level token from config
  - [x] 4.3: Configure JSON structured logging (`python-json-logger` v3) to stdout
  - [x] 4.4: Post startup confirmation message to `SLACK_CHANNEL_STARTUP` (default: `#general`)
  - [x] 4.5: Include version info in startup message: `"Lenie Bot connected. Version {version}. Backend: {url}"`
  - [x] 4.6: Handle startup failures gracefully (log error, exit non-zero)
  - [x] 4.7: Add `if __name__ == "__main__"` guard and `handler.start()` call
- [x] Task 5: Create `slack_bot/Dockerfile` (AC: #1, #4)
  - [x] 5.1: Base image: `python:3.11-slim` (consistent with backend)
  - [x] 5.2: Use `uv` from `ghcr.io/astral-sh/uv` for dependency installation
  - [x] 5.3: Install: `uv sync --frozen --no-dev --no-install-project`
  - [x] 5.4: Run as non-root user (`lenie-slack-bot`, UID 1001)
  - [x] 5.5: Entry point: `python -m src.main`
  - [x] 5.6: No `EXPOSE` — Socket Mode uses outbound WebSocket, no inbound port
- [x] Task 6: Update `infra/docker/compose.yaml` with slack profile (AC: #1)
  - [x] 6.1: Add `lenie-ai-slack-bot` service with `profiles: ["slack"]`
  - [x] 6.2: Set `build: ../../slack_bot` and `depends_on: [lenie-ai-server]`
  - [x] 6.3: Set `env_file: .env` (same .env as server, or separate slack.env)
  - [x] 6.4: Set `restart: unless-stopped`
- [x] Task 7: Create unit tests for `config.py` (NFR13)
  - [x] 7.1: Test `Config.require()` — returns value, returns default, exits on missing
  - [x] 7.2: Test `EnvBackend.load()` — reads from os.environ
  - [x] 7.3: Test `load_config()` — selects correct backend, returns singleton
  - [x] 7.4: Test `reset_config()` — clears singleton for test isolation
  - [x] 7.5: Target >80% coverage for `config.py`
- [x] Task 8: Code quality verification (NFR11, NFR12)
  - [x] 8.1: Run `ruff check slack_bot/` — zero warnings
  - [x] 8.2: Verify type hints on all public functions
  - [x] 8.3: Verify JSON logging output format (structured, no secrets)

## Dev Notes

### Critical Architecture Constraints

- **ZERO code dependencies on `backend/`** (NFR8): The Slack bot is an independent service — architecturally equivalent to Chrome Extension and React UI. It communicates with the backend ONLY via HTTP REST API. Do NOT import anything from `backend/library/`.
- **Self-contained config module**: Port the config_loader pattern from `backend/library/config_loader.py` into `slack_bot/src/config.py`. Same API (`Config.require()`), same backend support (env/vault/aws), but completely self-contained code. Do NOT create a shared package — keep it simple.
- **Socket Mode only**: No HTTP endpoint needed. `SocketModeHandler` maintains a WebSocket to Slack. No public URL, no ngrok, no `EXPOSE` in Dockerfile.
- **Docker Compose profiles**: The bot is optional. Use `profiles: ["slack"]` so it only starts when explicitly requested with `--profile slack`.
- **Separate pyproject.toml**: The bot is its own Python project. It does NOT share dependencies with the backend.

### Config Loader Pattern Reference

The bot's `config.py` MUST replicate the proven pattern from [backend/library/config_loader.py](../../backend/library/config_loader.py):

```python
# Core pattern to replicate:
class Config(dict):
    def require(self, key: str, default: str | None = None) -> str:
        value = self.get(key)
        if value is not None:
            return value
        if default is not None:
            return default
        logging.error("Missing configuration variable %s, exiting...", key)
        sys.exit(1)

# Bootstrap vars always from real environment:
_BOOTSTRAP_VARS = frozenset({
    "SECRETS_BACKEND", "VAULT_ADDR", "VAULT_TOKEN",
    "SECRETS_ENV", "ENV_DATA", "AWS_REGION", "PROJECT_CODE",
})

def load_config() -> Config:
    # 1. Load .env for bootstrap vars
    # 2. Read SECRETS_BACKEND (default: "env")
    # 3. Create backend instance, call .load()
    # 4. Cache as module-level singleton
    # 5. For vault/aws: inject into os.environ for compatibility
```

**Vault path**: `secret/{PROJECT_CODE}/{SECRETS_ENV}` (e.g., `secret/lenie/dev`)
**SSM path**: `/{PROJECT_CODE}/{SECRETS_ENV}/{key}` (e.g., `/lenie/dev/SLACK_BOT_TOKEN`)

### Required Configuration Variables

| Variable | Type | Required | Default | Description |
|----------|------|----------|---------|-------------|
| `SLACK_BOT_TOKEN` | secret | yes | — | Bot user OAuth token (`xoxb-...`) |
| `SLACK_APP_TOKEN` | secret | yes | — | App-level token for Socket Mode (`xapp-...`) |
| `STALKER_API_KEY` | secret | yes | — | API key for backend `x-api-key` header |
| `LENIE_API_URL` | config | yes | `http://lenie-ai-server:5000` | Backend base URL |
| `SLACK_CHANNEL_STARTUP` | config | no | `#general` | Channel for startup confirmation message |
| `SECRETS_BACKEND` | bootstrap | no | `env` | Secret backend: `env`, `vault`, `aws` |
| `SECRETS_ENV` | bootstrap | no | `dev` | Environment name for secret paths |
| `PROJECT_CODE` | bootstrap | no | `lenie` | Project code for secret paths |
| `VAULT_ADDR` | bootstrap | when vault | — | Vault server URL |
| `VAULT_TOKEN` | bootstrap | when vault | — | Vault authentication token |

**Note**: `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, and `STALKER_API_KEY` are NOT yet in [scripts/vars-classification.yaml](../../scripts/vars-classification.yaml) — that is scope of [Story 21-5](../../_bmad-output/planning-artifacts/epics.md#Story-215-Slack-App-Manifest--Setup-Documentation).

### Startup Confirmation Message

Post to `SLACK_CHANNEL_STARTUP` using `client.chat_postMessage()`:

```
Lenie Bot connected. Version 0.1.0. Backend: http://lenie-ai-server:5000
```

Use the Slack Web API client available from `app.client` after the App is initialized. The startup message should be sent AFTER Socket Mode connection is confirmed, not before.

### JSON Structured Logging

Use `python-json-logger` v3.x (NOT v4.0 — v4 has breaking parameter renames):

```python
import logging
from pythonjsonlogger import jsonlogger

handler = logging.StreamHandler()
handler.setFormatter(jsonlogger.JsonFormatter(
    fmt="%(asctime)s %(name)s %(levelname)s %(message)s"
))
logging.root.addHandler(handler)
logging.root.setLevel(logging.INFO)
```

Output to stdout — Docker `docker logs` collects automatically.

**Secret filtering**: Never log `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, `STALKER_API_KEY`, `VAULT_TOKEN` values. When logging config initialization, log key names only (e.g., "Loaded 5 config variables"), never values.

### Dockerfile Pattern

Follow [backend/Dockerfile](../../backend/Dockerfile) conventions:

```dockerfile
FROM ghcr.io/astral-sh/uv:latest AS uv
FROM python:3.11-slim

COPY --from=uv /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ src/

RUN useradd --create-home --uid 1001 lenie-slack-bot
USER lenie-slack-bot

CMD ["uv", "run", "python", "-m", "src.main"]
```

Key differences from backend:
- No `EXPOSE` (Socket Mode = outbound WebSocket)
- Simpler COPY (only `src/`, no `library/`)
- Different user UID (1001 vs backend 1000) to avoid conflicts

### Docker Compose Integration

Add to [infra/docker/compose.yaml](../../infra/docker/compose.yaml):

```yaml
lenie-ai-slack-bot:
  build: ../../slack_bot
  profiles: ["slack"]
  env_file: .env
  depends_on:
    - lenie-ai-server
  restart: unless-stopped
```

Start with: `docker compose --profile slack up -d`
Start everything: `docker compose --profile slack up -d` (adds bot to the regular stack)

The `.env` file in `infra/docker/` must include Slack tokens when using env backend. For vault backend, only bootstrap vars needed in `.env`.

### pyproject.toml Structure

```toml
[project]
name = "lenie-slack-bot"
version = "0.1.0"
requires-python = ">=3.11"

dependencies = [
    "slack-bolt>=1.27.0,<2.0.0",
    "slack-sdk>=3.40.0,<4.0.0",
    "python-json-logger>=3.0,<4.0",
    "python-dotenv>=1.0.0",
    "requests>=2.31.0",
]

[project.optional-dependencies]
vault = ["hvac>=2.1.0"]
aws = ["boto3>=1.34.0"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src"]

[tool.ruff]
line-length = 120
exclude = [".git", "__pycache__", ".venv"]

[tool.ruff.lint]
select = ["E", "F", "W"]
ignore = ["E501"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

**Note**: `requests` is included now because Story 21-2 (API client) will need it, and installing it from the start avoids a Docker image rebuild.

### Project Structure

```
slack_bot/                          # NEW top-level directory
├── Dockerfile
├── pyproject.toml
├── src/
│   ├── __init__.py                 # __version__ = "0.1.0"
│   ├── main.py                     # Entry point: Socket Mode connection, startup message
│   ├── config.py                   # Self-contained config loader (env/vault/aws)
│   ├── commands.py                 # (Story 21-3/21-4 — stub or empty for now)
│   └── api_client.py              # (Story 21-2 — stub or empty for now)
├── tests/
│   ├── __init__.py
│   └── unit/
│       ├── __init__.py
│       └── test_config.py
└── README.md                       # Minimal — full setup docs in Story 21-5
```

**Decision**: Create empty `commands.py` and `api_client.py` stubs (just module docstrings) so the project structure is complete from day one. This prevents reorganization in later stories.

### Anti-Patterns to Avoid

1. **Do NOT import `backend.library.config_loader`** — the bot must be self-contained
2. **Do NOT use `os.getenv()` directly in main.py** — use `cfg.require()` from config module
3. **Do NOT hardcode any URLs, tokens, or channel names** — all from config
4. **Do NOT use `logging.basicConfig()`** — set up JSON formatter explicitly
5. **Do NOT create a shared config package** — premature abstraction for 2 consumers
6. **Do NOT add slash command handlers in this story** — that is Story 21-3/21-4
7. **Do NOT pin exact versions** (e.g., `==1.27.0`) — use compatible ranges with upper bounds

### Testing Strategy

Run tests from the `slack_bot/` directory:

```bash
cd slack_bot
PYTHONPATH=. uvx pytest tests/unit/ -v
```

**Key test scenarios for config.py**:
- `Config.require("KEY")` returns value when present
- `Config.require("KEY", "default")` returns default when key missing
- `Config.require("KEY")` calls `sys.exit(1)` when key missing and no default
- `EnvBackend.load()` returns `os.environ` dict
- `load_config()` returns same instance on repeated calls (singleton)
- `reset_config()` clears the singleton

**Mocking pattern**: Use `unittest.mock.patch.dict(os.environ, {...})` to set test env vars. Mock `hvac.Client` for vault tests.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 21.1] — Story definition, acceptance criteria
- [Source: _bmad-output/planning-artifacts/prd.md#Technical Context] — Architecture, directory structure, API mapping, deployment
- [Source: backend/library/config_loader.py] — Config pattern to replicate (326 lines, 3 backends)
- [Source: backend/Dockerfile] — Docker build pattern (python:3.11-slim + uv)
- [Source: backend/pyproject.toml] — pyproject.toml structure reference (hatchling, ruff config)
- [Source: infra/docker/compose.yaml] — Docker Compose integration point (currently 3 services)
- [Source: scripts/vars-classification.yaml] — Secret classification SSOT (Slack vars NOT yet added — Story 21-5 scope)
- [Source: docs/secrets-management.md] — Secrets architecture documentation

### Git Intelligence

Recent work (Epic 20) established the config_loader pattern:
- `cfg.require()` / `cfg.get()` for config access
- Bootstrap vars always in real environment, never in Vault/SSM
- Vault path: `secret/lenie/dev` via hvac KV v2
- SSM path: `/lenie/dev/{key}` via boto3 GetParametersByPath
- `load_config()` as singleton factory
- `.env` file loaded via `find_dotenv(usecwd=True)` for scripts in subdirectories

### Latest Tech Versions

| Package | Latest Stable | Pin Range | Notes |
|---------|---------------|-----------|-------|
| `slack-bolt` | 1.27.0 (Nov 2025) | `>=1.27.0,<2.0.0` | Socket Mode built-in, Python 3.7+ |
| `slack-sdk` | 3.40.1 (Feb 2026) | `>=3.40.0,<4.0.0` | Auto-installed with slack-bolt |
| `python-json-logger` | 4.0.0 (Oct 2025) | `>=3.0,<4.0` | v4 breaks: renamed params, removed string config. Use v3 |
| `python-dotenv` | 1.1.0 | `>=1.0.0` | Stable API |
| `hvac` | 2.3.0 | `>=2.1.0` | KV v2 API stable |
| `requests` | 2.32.3 | `>=2.31.0` | For Story 21-2 API client |

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6

### Debug Log References
- hatchling build error: missing `README.md` — created minimal placeholder
- `test_defaults_to_env_backend`: project root `.env` sets `SECRETS_BACKEND=vault` — fixed by mocking `_load_bootstrap_dotenv`
- `test_loads_from_vault`: hvac lazy-imported, can't patch at module level — fixed with `patch.dict(sys.modules, {"hvac": mock})`
- ruff F821 in `main.py`: forward references — fixed with `from __future__ import annotations` and direct imports

### Completion Notes List
- All 8 tasks implemented and verified (24 unit tests pass, ruff clean)
- Config module is fully self-contained — zero imports from `backend/`
- python-json-logger pinned to v3 (v4 has breaking API changes)
- Slack Bolt lazy-imported in `main.py` to keep module testable without slack-bolt installed
- Backend regression check: 0 new failures (6 pre-existing unrelated failures)

### Code Review Fixes (2026-03-01)
- **C1 FIXED**: Startup message now sent AFTER `handler.connect()` confirms Socket Mode connection (was sent before connection)
- **H2 FIXED**: Added 6 unit tests for `main.py` (`test_main.py`: setup_logging, post_startup_message with defaults/channel/error handling)
- **M1 FIXED**: Removed dead `if TYPE_CHECKING: pass` block from `main.py`
- **M2 FIXED**: Dockerfile changed from `ENTRYPOINT` with hardcoded venv path to `CMD ["uv", "run", "python", "-m", "src.main"]`
- **M3 FIXED**: Added `.dockerignore` to exclude `.venv/`, `tests/`, `__pycache__/` from Docker build context
- **H1 FIXED**: Added missing `uv.lock` and new files to File List
- **B-80 CREATED**: Backlog item for adding `.dockerignore` to other directories (backend, web_interface_app2)
- Test runner note: `uvx pytest` doesn't work for `test_main.py` (pythonjsonlogger import). Use: `cd slack_bot && PYTHONPATH=. .venv/Scripts/python -m pytest tests/unit/ -v`

### File List
- `slack_bot/src/__init__.py` — package init with `__version__ = "0.1.0"` (NEW)
- `slack_bot/src/config.py` — self-contained config loader: Config, EnvBackend, VaultBackend, AWSSSMBackend (NEW)
- `slack_bot/src/main.py` — Socket Mode entry point, JSON logging, startup message (NEW, REVIEW-FIXED)
- `slack_bot/src/commands.py` — stub for Story 21-3/21-4 (NEW)
- `slack_bot/src/api_client.py` — stub for Story 21-2 (NEW)
- `slack_bot/pyproject.toml` — project config, pinned deps, ruff settings (NEW)
- `slack_bot/Dockerfile` — python:3.11-slim + uv, non-root user (NEW, REVIEW-FIXED)
- `slack_bot/.dockerignore` — Docker build context exclusions (NEW, REVIEW-ADDED)
- `slack_bot/uv.lock` — frozen dependency lock file (NEW)
- `slack_bot/README.md` — minimal placeholder (NEW)
- `slack_bot/tests/__init__.py` — test package init (NEW)
- `slack_bot/tests/unit/__init__.py` — unit test package init (NEW)
- `slack_bot/tests/unit/test_config.py` — 24 unit tests for config module (NEW)
- `slack_bot/tests/unit/test_main.py` — 6 unit tests for main module (NEW, REVIEW-ADDED)
- `infra/docker/compose.yaml` — added `lenie-ai-slack-bot` service with `profiles: ["slack"]` (MODIFIED)
