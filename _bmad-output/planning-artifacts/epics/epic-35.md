## Epic 35: MCP Server Foundation — Project Structure, Python SDK & Docker Integration

Developer has a working MCP server skeleton running as a Docker container on NAS, connected to the existing `lenie-net` network, with environment-variable configuration and a health check endpoint — ready to accept tool implementations.

**Stories:** 35-1, 35-2, 35-3

Implementation notes:
- Story 35-1 (Python project + dependencies) must be completed first
- Story 35-2 (Docker) depends on 35-1
- Story 35-3 (env config + health check) can be done in parallel with 35-2 but should be deployed together

### Story 35.1: Python Project Structure & MCP SDK Dependencies

As a **developer**,
I want a standalone Python project for the MCP server with all required dependencies defined,
so that the server is isolated from the backend Flask app and has a clean, reproducible build.

**Acceptance Criteria:**

**Given** no MCP server project exists
**When** the developer creates `mcp_server/` directory at project root
**Then** it contains:
```
mcp_server/
├── pyproject.toml          # uv project with all dependencies
├── uv.lock                 # generated lock file
├── .python-version         # pin to 3.12
├── src/
│   └── lenie_mcp/
│       ├── __init__.py
│       ├── server.py       # main FastMCP application entry point
│       ├── config.py       # env var loading (unified_config_loader)
│       ├── db.py           # SQLAlchemy session factory (reuse lenie pattern)
│       └── tools/
│           ├── __init__.py
│           ├── lenie.py    # Lenie tools
│           └── obsidian.py # Obsidian tools
└── Dockerfile
```

**Given** `pyproject.toml` is created
**When** `uv sync` is run in `mcp_server/`
**Then** it resolves without errors and installs:
- `mcp[cli]>=1.0` (official Python MCP SDK with FastMCP)
- `fastapi>=0.115`
- `uvicorn[standard]>=0.30`
- `sqlalchemy>=2.0,<3.0`
- `psycopg2-binary>=2.9` (or `asyncpg` if async SQLAlchemy is used)
- `pgvector>=0.3.0`
- `pydantic>=2.0`
- `unified-config-loader` (path dependency: `../shared_python/unified-config-loader/`)

**Given** `src/lenie_mcp/server.py` exists
**When** the file is inspected
**Then** it creates a `FastMCP` application instance named `"lenie-mcp"` with no tools registered yet (tools added in later epics)

**Given** the project is set up
**When** `cd mcp_server && uv run python -c "from lenie_mcp.server import mcp; print(mcp.name)"` is run
**Then** it prints `lenie-mcp` without errors

**Technical notes:**
- MCP SDK's `FastMCP` class is used (higher-level API vs raw `Server`) — decorator-based tool registration
- Transport: streamable HTTP (SSE-compatible) — required for Cloudflare MCP Portal
- Database access uses same `POSTGRESQL_*` env vars as backend — no new connection model
- `unified_config_loader` re-exported from `config.py` for consistent secret loading

### Story 35.2: Dockerfile & Docker Compose Integration (compose.nas.yaml)

As a **developer**,
I want the MCP server built as a Docker image and declared in `compose.nas.yaml`,
so that it starts alongside the other NAS containers and connects to the existing `lenie-net` network.

**Acceptance Criteria:**

**Given** `mcp_server/Dockerfile` exists
**When** `docker build -t lenie-mcp-server .` is run from `mcp_server/`
**Then** the image builds successfully using `python:3.12-slim` as base, installs dependencies via `uv`, and sets entry point to `uvicorn lenie_mcp.server:app --host 0.0.0.0 --port 8080`

**Given** `infra/docker/compose.nas.yaml` already defines containers for the NAS stack
**When** the developer adds the `lenie-mcp-server` service
**Then** the service definition includes:
- `image: lenie-mcp-server` (or `build: ../../mcp_server`)
- `container_name: lenie-mcp-server`
- `restart: unless-stopped`
- `ports: ["8080:8080"]`
- `networks: [lenie-net]`
- `env_file: mcp_server.env` (secrets — not committed)
- `env_file: mcp_server.env.example` (placeholder template — committed)
- health check: `GET /health` every 30s

**Given** `infra/docker/mcp_server.env.example` exists
**When** inspected
**Then** it contains placeholder entries for all required env vars (POSTGRESQL_*, OBSIDIAN_VAULT_PATH, SECRETS_BACKEND) with `<placeholder>` values — no real credentials

**Given** `infra/docker/mcp_server.env` is listed in `.gitignore`
**When** `.gitignore` is checked
**Then** the file is excluded from version control

**Given** the container starts
**When** `docker compose -f compose.nas.yaml up lenie-mcp-server -d` is run
**Then** `docker ps` shows the container running and `docker logs lenie-mcp-server` shows startup message without errors

**Technical notes:**
- `lenie-net` network already exists in `compose.nas.yaml` — MCP server joins as a new member
- Port 8080 is the container-internal port; Cloudflare Tunnel will expose it externally (Epic 39)
- `mcp_server.env` contains the same PostgreSQL credentials as `nas.env` — developer copies values

### Story 35.3: Environment Configuration & Health Check Endpoint

As a **developer**,
I want the MCP server to load configuration from environment variables and expose a `/health` endpoint,
so that the container can be monitored by Docker healthchecks and deployment can be verified.

**Acceptance Criteria:**

**Given** `src/lenie_mcp/config.py` exists
**When** the server starts
**Then** it loads the following env vars (via `unified_config_loader`) and fails fast with a descriptive error if required vars are missing:
- `POSTGRESQL_HOST`, `POSTGRESQL_DATABASE`, `POSTGRESQL_USER`, `POSTGRESQL_PASSWORD`, `POSTGRESQL_PORT` (required)
- `OBSIDIAN_VAULT_PATH` (required — absolute path to vault on NAS filesystem)
- `SECRETS_BACKEND` (optional, default: `env`)
- `MCP_SERVER_NAME` (optional, default: `lenie-mcp`)
- `LOG_LEVEL` (optional, default: `INFO`)

**Given** the server is running
**When** `GET /health` is called
**Then** it returns HTTP 200 with JSON:
```json
{"status": "ok", "server": "lenie-mcp", "version": "0.1.0"}
```

**Given** the database connection is unavailable at startup
**When** the server starts
**Then** startup proceeds (connection is lazy) and `/health` returns HTTP 200 (DB not checked at health endpoint level)

**Given** `OBSIDIAN_VAULT_PATH` points to a non-existent directory
**When** the server starts
**Then** it logs a WARNING (not a crash) — vault access errors are reported per-tool at invocation time

**Given** `LOG_LEVEL=DEBUG` is set
**When** any MCP tool is invoked
**Then** request details (tool name, parameters without secrets, timing) are logged at DEBUG level

**Technical notes:**
- FastMCP auto-generates the `/sse` and `/mcp` endpoints for the MCP protocol
- `/health` is a plain FastAPI route added separately (not an MCP tool)
- Structured logging (JSON format) recommended for NAS log aggregation
