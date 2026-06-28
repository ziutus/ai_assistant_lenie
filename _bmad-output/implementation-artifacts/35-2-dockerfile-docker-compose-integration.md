# Story 35.2: Dockerfile & Docker Compose Integration (compose.nas.yaml)

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **developer**,
I want the MCP server built as a Docker image and declared in `infra/docker/compose.nas.yaml`,
so that it starts alongside the other NAS containers and connects to the existing `lenie-net` network.

## Acceptance Criteria

1. **AC-1: Dockerfile builds successfully** — `infra/docker/Dockerfile.mcp` exists. Running `docker build -f infra/docker/Dockerfile.mcp -t lenie-mcp-server .` from the **project root** succeeds using `python:3.11-slim` as base, installs all dependencies via `uv sync --frozen --no-dev --no-install-project` (no extras needed — `mcp>=1.0` is in base deps), copies `backend/library/` and `backend/mcp_server/` into the image, and sets entry point to `uvicorn mcp_server.main:app --host 0.0.0.0 --port 8080`.

2. **AC-2: compose.nas.yaml service added** — `infra/docker/compose.nas.yaml` has a new `lenie-mcp-server` service with:
   - `image: 192.168.200.7:5005/lenie-mcp-server:latest`
   - `container_name: lenie-mcp-server`
   - `restart: unless-stopped`
   - `ports: ["8080:8080"]`
   - `networks: [lenie-net]`
   - `env_file: /share/Container/lenie-env/mcp_server.env`
   - healthcheck: `GET http://localhost:8080/healthz` every 30s, timeout 5s, retries 3

3. **AC-3: mcp_server.env.example committed** — `infra/docker/mcp_server.env.example` exists with placeholder values for all required env vars:
   ```
   POSTGRESQL_HOST=<placeholder>
   POSTGRESQL_DATABASE=<placeholder>
   POSTGRESQL_USER=<placeholder>
   POSTGRESQL_PASSWORD=<placeholder>
   POSTGRESQL_PORT=5432
   OBSIDIAN_VAULT_PATH=<placeholder>
   SECRETS_BACKEND=env
   MCP_SERVER_NAME=lenie-mcp
   LOG_LEVEL=INFO
   ```
   No real credentials — only `<placeholder>` values.

4. **AC-4: mcp_server.env excluded from git** — Running `git check-ignore infra/docker/mcp_server.env` confirms the file is ignored. (The root `.gitignore` already contains `*.env` — verify this rule catches the file.)

5. **AC-5: Image PYTHONPATH set** — Dockerfile sets `ENV PYTHONPATH=/app` so `from mcp_server.main import mcp` and `from library.services.document_service import DocumentService` work correctly at runtime without extra arguments.

6. **AC-6: Non-root user** — Dockerfile creates and uses `lenie-ai-client` (UID 1000, GID 1000) — matching existing `backend/Dockerfile` pattern.

7. **AC-7: Container starts (manual smoke test)** — After `docker build`, running:
   ```bash
   docker run --rm -p 8080:8080 \
     -e POSTGRESQL_HOST=127.0.0.1 -e POSTGRESQL_DATABASE=test \
     -e POSTGRESQL_USER=test -e POSTGRESQL_PASSWORD=test \
     -e OBSIDIAN_VAULT_PATH=/tmp \
     lenie-mcp-server
   ```
   The container starts without Python import errors. (The DB/Vault won't be reachable — that's OK; `/healthz` is implemented in Story 35-3.)

## Tasks / Subtasks

- [x] Task 1: Create `infra/docker/Dockerfile.mcp` (AC: 1, 5, 6)
  - [x] 1.1 Base image `python:3.11-slim`, install curl (healthcheck dep), install uv
  - [x] 1.2 Copy `shared_python/unified-config-loader/` (path dep)
  - [x] 1.3 Copy `backend/pyproject.toml` and `backend/uv.lock`, run `uv sync --frozen --no-dev --no-install-project`
  - [x] 1.4 Copy `backend/library ./library/` and `backend/mcp_server ./mcp_server/`
  - [x] 1.5 Set `ENV PYTHONPATH=/app` and `WORKDIR /app`
  - [x] 1.6 Create user `lenie-ai-client` (UID/GID 1000), switch to it
  - [x] 1.7 `EXPOSE 8080`, `ENTRYPOINT ["/app/.venv/bin/uvicorn", "mcp_server.main:app", "--host", "0.0.0.0", "--port", "8080"]`

- [x] Task 2: Add service to `infra/docker/compose.nas.yaml` (AC: 2)
  - [x] 2.1 Add `lenie-mcp-server` service block per AC-2
  - [x] 2.2 Healthcheck: `test: ["CMD", "curl", "-f", "http://localhost:8080/healthz"]` — note: endpoint implemented in Story 35-3; healthcheck will report unhealthy until then (expected)
  - [x] 2.3 Verify service is added BEFORE the `networks:` section

- [x] Task 3: Create `infra/docker/mcp_server.env.example` (AC: 3)
  - [x] 3.1 Create file with all 9 placeholder entries from AC-3
  - [x] 3.2 Add comment header: `# MCP Server environment variables — copy to /share/Container/lenie-env/mcp_server.env on NAS`

- [x] Task 4: Verify .gitignore coverage (AC: 4)
  - [x] 4.1 Run `git check-ignore infra/docker/mcp_server.env` (file need not exist — git check-ignore still reports)
  - [x] 4.2 If NOT ignored: add `infra/docker/mcp_server.env` to root `.gitignore` explicitly

- [x] Task 5: Smoke test build (AC: 7)
  - [x] 5.1 `docker build -f infra/docker/Dockerfile.mcp -t lenie-mcp-server .` — must succeed
  - [x] 5.2 `docker run --rm -e POSTGRESQL_HOST=127.0.0.1 ... lenie-mcp-server` — check no import errors in startup logs

## Dev Notes

### Architecture Overrides — Epic vs Established Reality

> **⚠️ CRITICAL: Story 35-1 established corrections that override epic-35.md. Use these, not the epic.**

| Aspect | Epic 35.2 says (WRONG) | Correct (from Story 35-1 Dev Notes) |
|--------|------------------------|-------------------------------------|
| Module path | `lenie_mcp.server:app` | `mcp_server.main:app` |
| Python version | 3.12 | **3.11** (project-wide standard) |
| Dockerfile location | `mcp_server/Dockerfile` | `infra/docker/Dockerfile.mcp` (build context = project root) |
| Health endpoint | `/health` | **`/healthz`** (D12, backend convention) |
| Project setup | Standalone `pyproject.toml` | Shared `backend/pyproject.toml` |

### Dockerfile Structure (mirroring `backend/Dockerfile`)

The MCP Dockerfile follows `backend/Dockerfile` closely but:
- Copies `mcp_server/` in addition to `library/`
- Does NOT copy `server.py` (Flask server is irrelevant)
- Sets PYTHONPATH=/app (not needed in Flask Dockerfile because Flask sets its own context)
- Exposes port 8080 (not 5000)
- Entry: uvicorn (not Flask's python server.py)

Reference structure:
```dockerfile
# syntax=docker/dockerfile:1.7
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY shared_python/unified-config-loader/ /shared_python/unified-config-loader/
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/library ./library/
COPY backend/mcp_server ./mcp_server/

RUN groupadd -g 1000 lenie-ai-client && \
    useradd -u 1000 -g lenie-ai-client -m lenie-ai-client && \
    chown -R 1000:1000 /app
USER lenie-ai-client

EXPOSE 8080
ENTRYPOINT ["/app/.venv/bin/uvicorn", "mcp_server.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

**Note**: `uv sync --frozen --no-dev --no-install-project` (no `--extra docker`) — the `docker` extra contains Flask-specific deps (aws-xray-sdk, etc.) not needed for MCP server. `mcp>=1.0` is in base deps.

### compose.nas.yaml — NAS env_file convention

Existing services use absolute paths to `/share/Container/lenie-env/` for env files (not relative paths). Follow this pattern:
```yaml
env_file:
  - /share/Container/lenie-env/mcp_server.env
```
The developer must manually copy `infra/docker/mcp_server.env.example` to `/share/Container/lenie-env/mcp_server.env` on the NAS and fill in real values from `nas.env`.

### Health Check Dependency on Story 35-3

The Docker `healthcheck` command (`curl -f http://localhost:8080/healthz`) references an endpoint that does NOT exist until Story 35-3 is implemented. This is expected:
- Story 35-2 and 35-3 can be implemented in parallel but **must be deployed together** (per epic-35.md dependency notes)
- Until 35-3 is done, the container will report `(health: starting)` → `(unhealthy)` — which is acceptable during development
- Do NOT add a placeholder `/healthz` in this story — that's 35-3's scope

### .gitignore Coverage

Root `.gitignore` line 2 contains `*.env` pattern which catches ALL `.env` files in the repository including `infra/docker/mcp_server.env`. No additional entry needed. Verify with:
```bash
git check-ignore -v infra/docker/mcp_server.env
```
Expected output: `.gitignore:2:*.env   infra/docker/mcp_server.env`

### ASGI App Entry Point

From Story 35-1 Debug Log: `mcp.get_asgi_app()` does NOT exist in mcp==1.27.0. The correct method is `mcp.streamable_http_app()`:
```python
# backend/mcp_server/main.py (already implemented in 35-1)
app = mcp.streamable_http_app()  # Returns starlette.applications.Starlette
```
uvicorn's entry point `mcp_server.main:app` references this `app` object. This is already working from Story 35-1.

### Build Context

The Dockerfile build context **must be the project root** (not `backend/` or `infra/docker/`) because it copies from:
- `shared_python/unified-config-loader/` (project root relative)
- `backend/pyproject.toml` (project root relative)
- `backend/library/` (project root relative)
- `backend/mcp_server/` (project root relative)

Build command (from project root):
```bash
docker build -f infra/docker/Dockerfile.mcp -t lenie-mcp-server .
```

For NAS deployment, the image is pushed to the private registry at `192.168.200.7:5005` (same as other images).

### Project Structure Notes

- New file: `infra/docker/Dockerfile.mcp` — follows naming convention of keeping Docker assets in `infra/docker/`
- Modified: `infra/docker/compose.nas.yaml` — adds `lenie-mcp-server` service
- New file: `infra/docker/mcp_server.env.example` — committed template (no secrets)
- NOT committed: `infra/docker/mcp_server.env` — covered by `*.env` gitignore rule

### References

- [Story 35-1 Dev Notes](35-1-python-project-structure-mcp-sdk-dependencies.md#dev-notes) — Architecture overrides, PYTHONPATH, entry point corrections
- [backend/Dockerfile](../../backend/Dockerfile) — Pattern to follow for base image, uv, user creation
- [infra/docker/compose.nas.yaml](../../infra/docker/compose.nas.yaml) — Existing NAS services pattern (env_file paths, network, registry URL)
- [Architecture D12](../../_bmad-output/planning-artifacts/architecture.md#d12) — `/healthz` as health endpoint
- [Architecture D5](../../_bmad-output/planning-artifacts/architecture.md#d5) — Auth-blind, trust Cloudflare upstream
- [backend/mcp_server/main.py](../../backend/mcp_server/main.py) — `app = mcp.streamable_http_app()` ASGI entry

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- Docker Desktop not running on Windows initially — resolved by switching to PowerShell for docker commands (WSL Docker integration requires Desktop to be running)
- NAS registry push skipped (NAS unreachable from current network) — not required by story ACs; deployment handled separately via `nas-deploy.sh`

### Completion Notes List

- Created `infra/docker/Dockerfile.mcp` following `backend/Dockerfile` pattern: `python:3.11-slim`, uv, `unified-config-loader` path dep, `uv sync --frozen --no-dev --no-install-project` (no `--extra docker`), copies `library/` and `mcp_server/`, `ENV PYTHONPATH=/app`, user `lenie-ai-client` UID/GID 1000, uvicorn entrypoint on port 8080
- Added `lenie-mcp-server` service to `infra/docker/compose.nas.yaml` before `networks:` section, with registry image, env_file, healthcheck curl on `/healthz`, lenie-net network
- Created `infra/docker/mcp_server.env.example` with 9 placeholder entries and NAS copy instruction header
- Verified `.gitignore:3:*.env` rule covers `infra/docker/mcp_server.env` — no additional entry needed
- Added `mcp-server` service to `infra/docker/nas-deploy.sh` (SVC_IMAGE, SVC_REGISTRY_IMAGE, SVC_DOCKERFILE, SVC_COMPOSE_NAME arrays + argument parser)
- Smoke test passed: `docker build` succeeded, `docker run` started without Python import errors — uvicorn serving on 0.0.0.0:8080, `StreamableHTTP session manager started`, `Application startup complete`

### File List

- `infra/docker/Dockerfile.mcp` (new)
- `infra/docker/compose.nas.yaml` (modified — added lenie-mcp-server service)
- `infra/docker/mcp_server.env.example` (new)
- `infra/docker/nas-deploy.sh` (modified — added mcp-server to all service maps)

### Change Log

- 2026-04-15: Implemented story 35-2 — Dockerfile.mcp, compose.nas.yaml service, mcp_server.env.example, nas-deploy.sh mcp-server support
- 2026-04-15: Code review fixes — (1) Dockerfile.mcp: selective COPY of mcp_server/ to exclude tests/ from production image; (2) compose.nas.yaml: added depends_on lenie-ai-db + healthcheck start_period 15s; (3) nas-deploy.sh: added MCP server URL to deploy summary output; (4) Dockerfile.mcp + backend/Dockerfile: pinned uv to 0.9.9 (was :latest); (5) .dockerignore: added backend/mcp_server/tests/ exclusion
