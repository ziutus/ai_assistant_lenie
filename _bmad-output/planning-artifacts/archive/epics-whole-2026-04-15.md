---
stepsCompleted:
  - step-01-validate-prerequisites
  - step-02-design-epics
  - step-03-create-stories
  - step-04-final-validation
status: complete
completedAt: '2026-04-13'
sprintNumber: 10
sprintName: 'MCP Server — mobile knowledge workflow'
status: complete
startedAt: '2026-04-13'
completedAt: '2026-04-13'
inputDocuments:
  - _bmad-output/planning-artifacts/prd.md
  - _bmad-output/planning-artifacts/architecture.md
  - _bmad-output/planning-artifacts/prd-validation-report.md
previousEpicsArchived: 'archive/epics-sprint9-sqlalchemy-orm-2026-04-13.md'
---

# lenie-server-2025 — Sprint 10 Epic Breakdown

## Overview

Sprint 10 scope: **MCP Server — mobile knowledge workflow**. This document decomposes PRD requirements (15 FRs + 16 NFRs) and Architecture decisions (Sprint 10 section — 12 decisions D1-D12, 8 implementation patterns, 13-step implementation sequence) into implementable epics and user stories.

The MVP gate (per PRD): Claude on mobile successfully reads an article from Lenie, creates/updates an Obsidian note, and the change propagates to all devices via Obsidian Sync.

## Requirements Inventory

### Functional Requirements

FR1: User can retrieve a list of unreviewed articles (limit 6 by default, newest first), showing title, source, size in KB, user note, date, and total count of unreviewed articles. User can request more or apply filters (source, type, date range, size).
FR2: User can retrieve the full markdown content and metadata of a specific article.
FR3: User can search articles by keyword or phrase across title, content, and user note. Results return title, source, snippet showing match context, and relevance ordering (most relevant first).
FR4: User can delete an article from the database.
FR5: When writing an Obsidian note linked to an article, system automatically associates the note path with the article. User can mark the article as reviewed when work on it is complete.
FR6: User can read the full content of an Obsidian note within `02-wiedza/`.
FR7: User can create a new Obsidian note within `02-wiedza/`.
FR8: User can overwrite an existing Obsidian note within `02-wiedza/`.
FR9: User can delete an Obsidian note within `02-wiedza/`.
FR10: User can list notes in a folder or subfolder within `02-wiedza/`.
FR11: System automatically saves the previous version of a note before every write operation.
FR12: System records the user prompt, content before, content after, and source article for each note change.
FR13: User can retrieve the version history of a specific note (date, user prompt, content before/after) to audit how the note evolved over time.
FR14: User can configure a Custom Connector in claude.ai pointing to the MCP server.
FR15: Claude on mobile can invoke all MCP tools (Lenie and Obsidian) through the Custom Connector.

### NonFunctional Requirements

NFR1: MCP tool responses complete within 5 seconds for article list and note read operations, as measured by MCP server response logging in production.
NFR2: Article list (`lenie_unreviewed_articles`) with default limit of 6 returns within 2 seconds, as measured by MCP server response logging.
NFR3: Note write operations (including version save to DB) complete within 3 seconds, as measured by MCP server response logging including DB write timing.
NFR4: All traffic between Claude and MCP server is encrypted via HTTPS (Cloudflare Tunnel), verified by tunnel configuration audit.
NFR5: MCP server cannot access filesystem outside `02-wiedza/` directory (path traversal prevention), verified by integration tests with traversal attempts.
NFR6: No credentials or secrets stored in MCP server Docker image — environment variables only, verified by image inspection in CI.
NFR7: Access to MCP server requires authentication via Cloudflare MCP Server Portal (Zero Trust OAuth) before reaching the server.
NFR8: MCP server is reachable from the public internet via Cloudflare Tunnel (no direct port exposure on NAS).
NFR9: Every note write operation creates a version record in `obsidian_note_versions` before overwriting — no exceptions.
NFR10: Database transactions for article operations are atomic — partial writes are not allowed.
NFR11: Note version history is retained indefinitely (no automatic purging).
NFR12: MCP server implements MCP protocol compatible with Claude Custom Connector (streamable HTTP transport).
NFR13: obsidian-headless container syncs vault changes to Obsidian Sync within 60 seconds of file write, as measured by file modification timestamp comparison between NAS and synced device.
NFR14: Vault changes written by MCP server propagate to phone and PC without requiring PC to be online (NAS-driven sync chain).
NFR15: Obsidian vault on NAS is continuously synchronized with all user devices via Obsidian Sync (bidirectional, conflict resolution by Obsidian).
NFR16: MCP server connects to existing PostgreSQL on `lenie-net` Docker network without additional configuration.

### Additional Requirements

**From Architecture Sprint 10 (decisions D1-D12):**

- **D1** — New SQLAlchemy ORM model `ObsidianNoteVersion` in `backend/library/db/models.py` + dedicated Alembic migration story for `obsidian_note_versions` table
- **D2** — Write coordinator pattern (DB version insert → commit → file overwrite) for `obsidian_write_note`; orphan version records logged as WARNING when detected
- **D4** — Single path security helper `backend/mcp_server/path_security.py::ensure_within_vault` called by every Obsidian tool (no bypass, enforced via code review)
- **D5** — Server is auth-blind; log `Cf-Access-Authenticated-User-Email` header value for audit trail; explicit deployment assumption that MCP server port is never directly exposed
- **D6** — All errors raised via helpers in `backend/mcp_server/errors.py` mapping 6 error codes (`article_not_found`, `note_not_found`, `note_path_invalid`, `vault_write_failed`, `database_unavailable`, `version_save_failed`) to JSON-RPC codes -32001 to -32006
- **D7** — Tool parameter validation via FastMCP + Pydantic type hints (no manual validators)
- **D8** — Direct import of `DocumentService` / `SearchService` from `backend/library/` with explicit Flask-independence verification as acceptance criterion on first story
- **D9** — `obsidian_note_history` returns unified diffs generated server-side via `difflib.unified_diff` (default limit 10, newest first)
- **D10** — `cloudflared` as separate Docker sidecar container in `compose.nas.yaml`, routing to `mcp-server:<port>`
- **D11** — `obsidian-headless` using pinned community image tag from `Belphemur/obsidian-headless-sync-docker` (never `:latest`)
- **D12** — Health check endpoint `/healthz` on internal-only port (127.0.0.1, not exposed via tunnel) for Docker healthcheck directive
- **Log rotation** (validation resolution) — `logging: driver: json-file, max-size: 10m, max-file: 3` on all 3 new Docker services in `compose.nas.yaml`
- **E2E test mandatory** (validation resolution) — full sync chain integration test on NAS is mandatory (not optional), validates PRD MVP gate

**From Architecture Sprint 10 Implementation Patterns:**

- Tool naming: `<scope>_<verb>_<noun>` in `snake_case` (e.g., `lenie_get_article`, `obsidian_write_note`)
- Parameter naming: `snake_case`, path params always vault-relative, never absolute
- Return shape: plain `dict`/`list[dict]`, list endpoints use `{"items": [...], "total": N, "limit": L, "offset": O}` envelope
- Timestamps: ISO 8601 UTC strings, never epoch integers
- SQLAlchemy session: one per tool invocation, variable named `db_session` (not `session`) to avoid conflation with FastMCP session concept
- Logging: `INFO` for tool invocations (tool name, user email, param summary — excluding sensitive content), `WARNING` for orphan versions and path traversal attempts, `ERROR` for unexpected exceptions
- Service invocation priority: prefer existing `DocumentService` / `SearchService` → if not covered, add method to existing service → if new domain, SQLAlchemy ORM query → NEVER raw SQL

**From Architecture Sprint 10 Starter Template Evaluation:**

- No external starter/scaffolding; brownfield extension using `mcp` SDK v1.12.4+ with FastMCP API
- Transport: `streamable-http` with `stateless_http=True, json_response=True`
- Project structure: `backend/mcp_server/` subtree (peer to `backend/server.py`, `backend/imports/`)
- Deployment: 3 new Docker services in `compose.nas.yaml` (`mcp-server`, `cloudflared`, `obsidian-headless`)

**From Architecture Sprint 10 Implementation Sequence (13 ordered stories):**

1. Project initialization — `backend/mcp_server/` skeleton, `uv add mcp`, Docker service placeholder
2. Service reuse verification (D8) — validates PRD assumption about Flask decoupling
3. Alembic migration for `obsidian_note_versions` (D1)
4. Error module + enum (D6) — `backend/mcp_server/errors.py`
5. Path security helper (D4) — `backend/mcp_server/path_security.py` with exhaustive tests
6. Lenie tools (FR1-FR4)
7. Obsidian read-only tools (FR6, FR10)
8. Obsidian write tools (FR7, FR8, FR9) — uses D2 coordinator pattern
9. Note history tool (FR13) — uses D9 query + diff
10. Review-mark logic (FR5) — tied to `obsidian_write_note`
11. Health endpoint (D12) + Docker healthcheck
12. Cloudflare Tunnel sidecar (D10) + obsidian-headless container (D11) + log rotation
13. End-to-end integration test (MANDATORY — validates PRD MVP gate)

### FR Coverage Map

| FR | Epic | Description |
|----|------|-------------|
| FR1 | Epic 1 | `lenie_unreviewed_articles` — list unreviewed articles with filters |
| FR2 | Epic 1 | `lenie_get_article` — fetch full markdown + metadata |
| FR3 | Epic 1 | `lenie_search_articles` — keyword/phrase search with snippets |
| FR4 | Epic 1 | `lenie_delete_article` — remove article from DB |
| FR5 | Epic 4 | Auto-link note path to article on write + mark-as-reviewed |
| FR6 | Epic 2 | `obsidian_read_note` — read note content in `02-wiedza/` |
| FR7 | Epic 3 | `obsidian_create_note` — create new note |
| FR8 | Epic 3 | `obsidian_write_note` — overwrite existing note |
| FR9 | Epic 3 | `obsidian_delete_note` — delete note |
| FR10 | Epic 2 | `obsidian_list_notes` — list folder/subfolder contents |
| FR11 | Epic 3 | Automatic pre-write version save via D2 write coordinator |
| FR12 | Epic 3 | Record user prompt + content before/after + source article |
| FR13 | Epic 3 | `obsidian_note_history` — retrieve version history with unified diffs |
| FR14 | Epic 1 | Custom Connector configuration against MCP server |
| FR15 | Epic 1 | Claude mobile invokes MCP tools through Custom Connector |

Coverage: 15/15 FRs mapped.

## Epic List

### Epic 1: MCP Foundation — Claude Mobile Reads Lenie Articles
After a one-time Custom Connector configuration, the user can browse, search, read, and delete unreviewed Lenie articles from Claude mobile. Establishes the MCP server foundation (project skeleton, service reuse verification, error module, health endpoint, Cloudflare Tunnel, auth-blind logging, log rotation) alongside the four Lenie tools.
**FRs covered:** FR1, FR2, FR3, FR4, FR14, FR15
**Architecture decisions in scope:** D5, D6, D7, D8, D10, D12 + log rotation
**Implementation sequence items:** 1, 2, 4, 6, 11, 12 (Cloudflare Tunnel portion)

### Epic 2: Obsidian Vault Read Access
User can browse folders and read existing notes in `02-wiedza/` from Claude mobile (e.g., to reference prior knowledge during a conversation). Introduces the path security helper that every subsequent Obsidian tool will reuse.
**FRs covered:** FR6, FR10
**Architecture decisions in scope:** D4
**Implementation sequence items:** 5, 7

### Epic 3: Obsidian Note Authoring with Version History
User can create, overwrite, and delete notes in `02-wiedza/` with automatic pre-write versioning (user prompt, content before/after, source article) and can retrieve server-generated unified diffs for audit.
**FRs covered:** FR7, FR8, FR9, FR11, FR12, FR13
**Architecture decisions in scope:** D1, D2, D9
**Implementation sequence items:** 3, 8, 9

### Epic 4: End-to-End Review Workflow & Multi-Device Sync
User closes the article→note loop on mobile: writing a note auto-links to the source article, `mark_reviewed` flips article state, and vault changes propagate to phone and PC via Obsidian Sync without PC needing to be online. Delivers the PRD MVP gate via a mandatory end-to-end integration test.
**FRs covered:** FR5
**Architecture decisions in scope:** D11 (obsidian-headless) + E2E test mandate
**Implementation sequence items:** 10, 12 (obsidian-headless portion), 13

---

## Epic 1: MCP Foundation — Claude Mobile Reads Lenie Articles

**Goal:** After a one-time Custom Connector configuration, the knowledge worker can browse, search, read, and delete unreviewed Lenie articles from Claude mobile. Establishes the MCP server foundation (project skeleton, service-reuse verification, error taxonomy, health endpoint, Cloudflare Tunnel, auth-blind logging, log rotation) alongside the four Lenie tools.

### Story 1.1: Project skeleton & FastMCP bootstrap

As a knowledge worker,
I want a running MCP server skeleton reachable over HTTP inside the `lenie-net` Docker network,
So that subsequent stories can register tools against a working transport layer.

**Acceptance Criteria:**

**Given** an empty `backend/mcp_server/` subtree
**When** I add the `mcp` SDK (v1.12.4+) via `uv add mcp` and create a minimal FastMCP server configured with `stateless_http=True, json_response=True` on `streamable-http` transport
**Then** a new `mcp-server` service in `infra/docker/compose.nas.yaml` starts successfully and joins `lenie-net` (NFR16)
**And** the project layout follows `backend/mcp_server/` as a peer to `backend/server.py` and `backend/imports/`
**And** the server exposes an MCP endpoint answering initialize requests but registers zero tools at this point
**And** `uv lock` is updated and `.venv_wsl` is re-synced per the project's WSL workflow
**And** no secrets or credentials are embedded in the Docker image (NFR6)

### Story 1.2: Service-reuse verification (Flask decoupling)

As a knowledge worker,
I want proof that `DocumentService` and `SearchService` can be imported and used without initializing Flask,
So that the PRD assumption about sharing business logic between Flask and MCP is validated before we build tools on top of it (D8).

**Acceptance Criteria:**

**Given** the existing `backend/library/` service classes
**When** an automated test imports `DocumentService` and `SearchService` in a process that never imports `flask` or instantiates `server.py`
**Then** both services instantiate and execute a read-only method against the development database without raising
**And** the test runs under `cd backend && PYTHONPATH=. uvx pytest tests/integration/ -v` in CI
**And** the test fails loudly (not skipped) if any Flask import sneaks into the service import graph
**And** the verification result is documented in the MCP server README or module docstring

### Story 1.3: Error module with 6-code taxonomy

As a knowledge worker,
I want every MCP tool to raise errors through a single helper module mapping domain error codes to JSON-RPC codes,
So that Claude receives consistent, machine-parseable errors regardless of which tool failed (D6).

**Acceptance Criteria:**

**Given** no error module exists in `backend/mcp_server/`
**When** I create `backend/mcp_server/errors.py` exposing helpers for the six defined codes (`article_not_found`, `note_not_found`, `note_path_invalid`, `vault_write_failed`, `database_unavailable`, `version_save_failed`)
**Then** each helper raises an exception that FastMCP serializes to JSON-RPC codes `-32001` through `-32006` respectively
**And** the module has unit tests covering all six codes and asserting the JSON-RPC code + message shape
**And** the module exposes no raw exception classes to tool code — only helper functions that raise

### Story 1.4: Lenie article tools (list, get, search, delete)

As a knowledge worker using Claude mobile,
I want four Lenie tools to discover, read, search, and delete unreviewed articles,
So that I can triage my reading queue entirely from my phone (FR1–FR4).

**Acceptance Criteria:**

**Given** Stories 1.1–1.3 are complete and PostgreSQL is reachable on `lenie-net`
**When** the MCP server registers `lenie_unreviewed_articles`, `lenie_get_article`, `lenie_search_articles`, and `lenie_delete_article` using FastMCP + Pydantic type hints (D7)
**Then** each tool follows the naming convention `<scope>_<verb>_<noun>` in `snake_case` and uses a `db_session` variable (one session per invocation)
**And** `lenie_unreviewed_articles` returns `{"items": [...], "total": N, "limit": L, "offset": O}` with default `limit=6`, newest first, supporting filters for source, type, date range, and size (FR1), and completes within 2 seconds at default limit (NFR2)
**And** `lenie_get_article` returns the full markdown content and metadata for a given article id/uuid, raising `article_not_found` via the error module when missing (FR2)
**And** `lenie_search_articles` performs keyword/phrase search across title, content, and user note, returning title, source, match snippet, and relevance ordering (FR3)
**And** `lenie_delete_article` removes the article row atomically (NFR10) and raises `article_not_found` when the id/uuid does not match (FR4)
**And** all tools return plain `dict`/`list[dict]` with ISO 8601 UTC timestamps (never epoch integers)
**And** all tools implement service invocation priority: existing `DocumentService`/`SearchService` first, then added service method, then ORM query — never raw SQL
**And** each tool invocation logs at `INFO` with tool name, user email (from `Cf-Access-Authenticated-User-Email` header when present), and non-sensitive param summary
**And** tool list/read operations complete within 5 seconds as measured by response logging (NFR1)

### Story 1.5: Health endpoint and Docker healthcheck

As a knowledge worker,
I want the MCP server to expose a `/healthz` endpoint bound to `127.0.0.1` that Docker uses for health checks,
So that the container is restarted automatically when the server becomes unresponsive, without exposing health data through the tunnel (D12).

**Acceptance Criteria:**

**Given** the MCP server from Story 1.1 is running
**When** I add a `/healthz` endpoint bound to `127.0.0.1` only (not advertised through `streamable-http`) returning `200 OK` with a small JSON status body
**Then** the `mcp-server` service in `compose.nas.yaml` declares a Docker `HEALTHCHECK` directive invoking the endpoint on loopback
**And** `docker ps` reports the container as `healthy` when the server accepts requests and `unhealthy` after configurable consecutive failures
**And** the `/healthz` endpoint is unreachable from outside the container (not exposed via Cloudflare Tunnel)
**And** the endpoint does not require authentication and does not leak database or filesystem state beyond a liveness status

### Story 1.6: Cloudflare Tunnel sidecar, auth-blind logging, and log rotation

As a knowledge worker,
I want Claude mobile to reach the MCP server via an authenticated Cloudflare Tunnel, with every tool invocation logging the authenticated user email and with container logs rotated to avoid disk bloat,
So that I can configure a Custom Connector in claude.ai and actually invoke tools end-to-end from my phone (FR14, FR15).

**Acceptance Criteria:**

**Given** stories 1.1, 1.3, 1.4, and 1.5 are complete
**When** I add a `cloudflared` sidecar container in `compose.nas.yaml` routing public tunnel traffic to `mcp-server:<port>` (D10) and the MCP server logs `Cf-Access-Authenticated-User-Email` header values on every tool invocation (D5)
**Then** no MCP server port is exposed directly on the NAS host — only the tunnel accepts public traffic (NFR8)
**And** all traffic between Claude and the MCP server is HTTPS-encrypted through the tunnel (NFR4)
**And** access is gated by Cloudflare MCP Server Portal (Zero Trust OAuth) before any request reaches the server (NFR7)
**And** the MCP server itself is auth-blind — it trusts the `Cf-Access-Authenticated-User-Email` header but performs no authentication logic of its own (D5)
**And** all three new Docker services (`mcp-server`, `cloudflared`, plus any obsidian-headless placeholder) declare `logging: driver: json-file, options: { max-size: 10m, max-file: 3 }`
**And** a Custom Connector configured in claude.ai against the tunnel URL successfully initializes and lists all four `lenie_*` tools (FR14)
**And** Claude mobile can invoke each of the four Lenie tools through the Custom Connector and receive valid responses (FR15)
**And** the MCP server implements an MCP protocol version compatible with Claude Custom Connector over `streamable-http` (NFR12)

---

## Epic 2: Obsidian Vault Read Access

**Goal:** The knowledge worker can browse folders and read existing notes in `02-wiedza/` from Claude mobile — useful alone (e.g., referencing prior knowledge in a conversation) before any write capability lands.

### Story 2.1: Path security helper `ensure_within_vault`

As a knowledge worker,
I want every Obsidian tool to route path arguments through a single security helper that rejects traversal, absolute paths, and symlink escapes,
So that no MCP tool can read or modify files outside `02-wiedza/` (D4, NFR5).

**Acceptance Criteria:**

**Given** no path security module exists in `backend/mcp_server/`
**When** I create `backend/mcp_server/path_security.py` exposing `ensure_within_vault(relative_path: str) -> Path`
**Then** the helper resolves the path relative to the configured vault root and returns the resolved absolute `Path` only when it stays within the vault root after full symlink resolution
**And** the helper raises a domain error mapped to `note_path_invalid` (via the Story 1.3 error module) for: absolute paths, paths containing `..` components that escape the root, paths containing null bytes, symlinks pointing outside the vault, and paths escaping via Windows/WSL drive-letter tricks
**And** the helper logs every rejection at `WARNING` with the offending path (truncated if long) and the authenticated user email
**And** unit tests cover every rejection class with concrete malicious inputs and at least one positive control (valid nested path)
**And** the helper is the only sanctioned way for tools to resolve vault paths — enforced via code review (documented in module docstring)

### Story 2.2: Obsidian read-only tools (`obsidian_read_note`, `obsidian_list_notes`)

As a knowledge worker using Claude mobile,
I want to list folder contents and read note bodies within `02-wiedza/`,
So that I can reference my existing knowledge notes from my phone without opening Obsidian (FR6, FR10).

**Acceptance Criteria:**

**Given** Story 2.1 is complete and the Obsidian vault is mounted into the `mcp-server` container at the configured vault root
**When** the MCP server registers `obsidian_read_note(path: str)` and `obsidian_list_notes(folder: str)` following the `<scope>_<verb>_<noun>` naming convention
**Then** both tools pass every caller-supplied path through `ensure_within_vault` before any filesystem access (D4)
**And** `obsidian_read_note` returns the full note content plus metadata (path relative to vault root, size in bytes, last-modified timestamp as ISO 8601 UTC), raising `note_not_found` via the error module when the file is missing
**And** `obsidian_list_notes` returns `{"items": [...], "total": N, "limit": L, "offset": O}` where each item contains relative path, type (`file`/`folder`), size, and last-modified timestamp in ISO 8601 UTC
**And** both tools use FastMCP + Pydantic type hints for parameter validation (D7) and raise domain errors through the Story 1.3 error module (never raw exceptions)
**And** both tools log invocations at `INFO` with tool name, user email, and param summary
**And** neither tool reveals absolute host paths in return values or error messages (only vault-relative paths)
**And** list/read operations complete within 5 seconds as measured by response logging (NFR1)

---

## Epic 3: Obsidian Note Authoring with Version History

**Goal:** The knowledge worker can create, overwrite, and delete notes in `02-wiedza/` from Claude mobile, with every write automatically preceded by a version record (user prompt, content before/after, source article), and can retrieve server-generated unified diffs for audit.

### Story 3.1: Alembic migration and `ObsidianNoteVersion` ORM model

As a knowledge worker,
I want a dedicated table to store every pre-write snapshot of an Obsidian note along with the triggering context,
So that subsequent write tools can persist immutable version history before overwriting any file (D1).

**Acceptance Criteria:**

**Given** no `obsidian_note_versions` table exists in the database
**When** I add `ObsidianNoteVersion` to `backend/library/db/models.py` and create a dedicated Alembic migration
**Then** the table stores, at minimum: primary key, note path (relative to vault root), user prompt, content before (nullable for create), content after (nullable for delete), source article id/uuid (nullable), authenticated user email, and created-at timestamp (UTC)
**And** indexes support efficient history queries by note path and by created-at DESC
**And** the migration runs cleanly `up` and `down` against the NAS PostgreSQL (`192.168.200.7:5434`, database `lenie-ai`) — verification is done against NAS, not local Docker
**And** the migration does not alter the `web_documents` or `websites_embeddings` tables
**And** the ORM model is importable under the `cd backend && PYTHONPATH=. uvx pytest` workflow and covered by a round-trip unit test (insert + select)
**And** the `.venv_wsl` is resynced if any new Python dependency is introduced by the migration

### Story 3.2: Write coordinator for `obsidian_write_note` (overwrite)

As a knowledge worker,
I want overwriting an existing note to first persist a version record and only then write the file,
So that no pre-write state can be lost and orphan versions are detectable if the file write fails (FR8, FR11, FR12, D2, NFR9).

**Acceptance Criteria:**

**Given** Stories 2.1 and 3.1 are complete
**When** the MCP server registers `obsidian_write_note(path: str, content: str, user_prompt: str, source_article_id: str | None)` using FastMCP + Pydantic (D7)
**Then** the path passes through `ensure_within_vault` before any DB or filesystem access (D4)
**And** the tool raises `note_not_found` via the Story 1.3 error module if the file does not already exist (create is handled by Story 3.3)
**And** the write coordinator executes in this exact order: (1) read current file content, (2) INSERT into `obsidian_note_versions` with content-before = current content and content-after = new content, (3) COMMIT the DB transaction, (4) overwrite the file on disk; no file write occurs before DB commit (NFR9)
**And** if the DB INSERT or COMMIT fails, the tool raises `version_save_failed` and does not touch the file
**And** if the file write fails after a successful DB commit, the tool raises `vault_write_failed` and logs an orphan version record detection at `WARNING` (content-after exists in DB but not on disk)
**And** the full operation (including version save) completes within 3 seconds as measured by response logging that includes DB write timing (NFR3)
**And** tool invocations are logged at `INFO` with tool name, user email, note path, and prompt length (prompt content itself not logged verbatim)
**And** the tool returns a plain `dict` describing the resulting note (path, new size, last-modified ISO 8601 UTC timestamp, version id)

### Story 3.3: Create and delete tools (`obsidian_create_note`, `obsidian_delete_note`)

As a knowledge worker,
I want to create new notes and delete existing ones from Claude mobile with the same versioning guarantees as overwrite,
So that every state transition of a note is captured in history, including initial creation and final deletion (FR7, FR9, FR11, FR12, NFR9).

**Acceptance Criteria:**

**Given** Stories 2.1, 3.1, and 3.2 are complete
**When** the MCP server registers `obsidian_create_note(path, content, user_prompt, source_article_id)` and `obsidian_delete_note(path, user_prompt)`
**Then** both tools route path arguments through `ensure_within_vault` (D4) and raise via the error module (D6)
**And** `obsidian_create_note` raises `note_path_invalid` through the error module if a file already exists at the target path (no silent overwrite — that is Story 3.2's job)
**And** `obsidian_create_note` follows the D2 coordinator pattern with content-before = NULL and content-after = the new content, committing the version record before writing the file (NFR9)
**And** `obsidian_delete_note` raises `note_not_found` via the error module if the file does not exist
**And** `obsidian_delete_note` follows the D2 coordinator pattern with content-before = current content and content-after = NULL, committing the version record before deleting the file from disk (NFR9)
**And** both tools complete within 3 seconds including version save (NFR3)
**And** both tools log invocations at `INFO` and detect orphan versions at `WARNING` when a filesystem operation fails after a successful DB commit
**And** each tool returns a plain `dict` with the resulting state (path, version id, and for create: new size + last-modified timestamp)

### Story 3.4: Note history with server-side unified diffs (`obsidian_note_history`)

As a knowledge worker,
I want to retrieve the version history of a note with ready-to-read unified diffs between consecutive versions,
So that I can audit how a note evolved without computing diffs on the client (FR13, D9, NFR11).

**Acceptance Criteria:**

**Given** Stories 3.1–3.3 are complete and at least one note has multiple versions
**When** the MCP server registers `obsidian_note_history(path: str, limit: int = 10, offset: int = 0)`
**Then** the path passes through `ensure_within_vault` (D4)
**And** the tool returns `{"items": [...], "total": N, "limit": L, "offset": O}` with items ordered newest first
**And** each item contains: version id, created-at (ISO 8601 UTC), authenticated user email, user prompt, source article id (nullable), and a `diff` field containing a server-generated `difflib.unified_diff` between content-before and content-after
**And** diff generation happens server-side — the client never receives raw content-before/content-after in the normal history response
**And** default `limit=10` and pagination works (`offset` parameter honored)
**And** no version records are purged automatically — history is retained indefinitely (NFR11)
**And** the tool raises `note_not_found` if no versions exist for the given path (and the file itself does not exist either)
**And** the tool logs invocations at `INFO` with tool name, user email, note path, and the returned item count

---

## Epic 4: End-to-End Review Workflow & Multi-Device Sync

**Goal:** The knowledge worker closes the article→note loop on mobile — writing a note auto-links it to the source article, `mark_reviewed` flips article state, and vault changes propagate to phone and PC via Obsidian Sync without PC needing to be online. Delivers the PRD MVP gate via a mandatory manual end-to-end integration test.

### Story 4.1: Auto-link note path to article and `lenie_mark_reviewed` tool

As a knowledge worker,
I want writing an Obsidian note with a source article to automatically associate the note path with that article, and I want an explicit tool to mark an article as reviewed,
So that the article→note relationship is captured without manual bookkeeping and I can flip review state either implicitly (via note write) or explicitly (via a dedicated tool) (FR5).

**Acceptance Criteria:**

**Given** Stories 3.2 and 3.3 are complete and `web_documents` has the `obsidian_note_paths` and `reviewed_at` columns populated by the existing schema
**When** `obsidian_write_note` or `obsidian_create_note` is invoked with a non-null `source_article_id`
**Then** the article row referenced by `source_article_id` has the written note path appended to `obsidian_note_paths` (idempotent — no duplicate entries if the same path is already present)
**And** the note-path association is written atomically in the same DB transaction as the version record (NFR10) — partial writes are not permitted
**And** the tool raises `article_not_found` via the Story 1.3 error module when `source_article_id` does not match any article
**When** the MCP server additionally registers `lenie_mark_reviewed(article_id: str)`
**Then** the tool sets `reviewed_at` on the referenced article to the current UTC timestamp and returns the updated article stub (id, reviewed_at)
**And** `lenie_mark_reviewed` raises `article_not_found` via the error module when the id does not match
**And** both auto-link behavior and explicit marking coexist: `obsidian_write_note`/`obsidian_create_note` with `source_article_id` append to `obsidian_note_paths` but do NOT automatically set `reviewed_at` — `reviewed_at` only flips when `lenie_mark_reviewed` is explicitly invoked
**And** all three tools log invocations at `INFO` with tool name, user email, article id, and (for write tools) note path
**And** unit and integration tests cover: successful auto-link, idempotent re-link, missing article → error, explicit mark-reviewed, and the interaction ordering (auto-link does not imply reviewed)

### Story 4.2: `obsidian-headless` sync sidecar container with log rotation

As a knowledge worker,
I want an `obsidian-headless` Docker container running on the NAS that continuously syncs the vault to Obsidian Sync,
So that changes written by the MCP server propagate to my phone and PC through NAS-driven sync without requiring my PC to be online (D11, NFR13, NFR14, NFR15).

**Acceptance Criteria:**

**Given** Epic 1 has introduced `compose.nas.yaml` with `mcp-server` and `cloudflared` services
**When** I add an `obsidian-headless` service to `compose.nas.yaml` using a pinned community image tag from `Belphemur/obsidian-headless-sync-docker` (never `:latest`) (D11)
**Then** the container mounts the same Obsidian vault volume that `mcp-server` writes to, with matching file permissions so both containers can coexist on the vault
**And** the container is configured with the required Obsidian Sync credentials via environment variables (no credentials in the image — NFR6) and the actual values are stored in Vault/SSM (not `.env` beyond bootstrap) per the project's secrets workflow
**And** the container declares `logging: driver: json-file, options: { max-size: 10m, max-file: 3 }` (log rotation resolution)
**And** a file modification written by `mcp-server` to the vault propagates to Obsidian Sync within 60 seconds, as measured by comparing file modification timestamps between the NAS and a synced device (NFR13)
**And** the sync chain works with the PC offline — a change written via MCP from the phone reaches another synced device without the PC ever being online during the window (NFR14)
**And** the Obsidian vault on the NAS is continuously bidirectionally synchronized with all configured devices via Obsidian Sync (NFR15)
**And** a deployment runbook entry in the docs/ tree documents how to obtain/rotate the Obsidian Sync credentials for this container
**And** container startup and successful sync initialization are observable in container logs (used as manual health check, since Obsidian Sync exposes no health endpoint)

### Story 4.3: Manual end-to-end integration test (PRD MVP gate)

As a knowledge worker,
I want a documented manual end-to-end test that validates the full sync chain — Claude mobile → MCP → DB + vault → Obsidian Sync → second device,
So that I can explicitly verify the PRD MVP gate has been met before calling Sprint 10 done (E2E test mandate from validation).

**Acceptance Criteria:**

**Given** Stories 1.1–4.2 are complete and deployed to the NAS stack
**When** a runbook is added under `docs/` (e.g. `docs/CICD/NAS_MCP_E2E_Test.md` or similar) describing the MVP-gate verification procedure
**Then** the runbook is executed manually (no CI automation — CI is currently inactive per project docs) and records pass/fail in an attached checklist
**And** the runbook covers at least these verification steps, in order:
  1. Claude mobile (via Custom Connector) invokes `lenie_unreviewed_articles` and receives a list of unreviewed articles
  2. Claude mobile invokes `lenie_get_article` on one article and receives its full markdown
  3. Claude mobile invokes `obsidian_create_note` or `obsidian_write_note` against `02-wiedza/` with that article's id as `source_article_id` and a user prompt
  4. The new/updated note appears on a second synced device (e.g., laptop Obsidian client) within 60 seconds (NFR13)
  5. The article's `obsidian_note_paths` column in the NAS PostgreSQL now contains the written note path (verified via `psql` against NAS: `PGPASSWORD=postgres "/c/Program Files/PostgreSQL/18/bin/psql.exe" -h 192.168.200.7 -p 5434 -U postgres -d lenie-ai`)
  6. A version row exists in `obsidian_note_versions` with matching user prompt and source article id
  7. Claude mobile invokes `lenie_mark_reviewed` for the same article and `reviewed_at` is now set in the DB
  8. The entire round-trip (steps 3 → 4) completes with the PC kept offline, proving NAS-driven sync (NFR14)
**And** the runbook explicitly calls out that this test is manual and mandatory before declaring the MVP gate met — it is not optional and must be re-run after any change that touches the sync chain
**And** a pass of this runbook is the formal definition of Sprint 10 acceptance

---
