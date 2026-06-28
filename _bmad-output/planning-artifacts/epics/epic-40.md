## Epic 40: End-to-End Integration — obsidian-headless, Claude Custom Connector & MVP Acceptance

The complete mobile knowledge workflow is operational: obsidian-headless syncs vault changes from NAS to all devices via Obsidian Sync, Claude's Custom Connector is configured to reach the MCP server, and the MVP gate is formally validated — Claude on mobile successfully creates an Obsidian note from a Lenie article.

**Stories:** 40-1, 40-2, 40-3

Implementation notes:
- Story 40-1 (obsidian-headless) and Story 40-2 (Custom Connector) can be done in parallel
- Story 40-3 (end-to-end acceptance test) requires 40-1 and 40-2 to be complete, and all Epics 35–39 to be deployed
- Epic 40 is the sprint's definition of done — Story 40-3 is the MVP gate

### Story 40.1: obsidian-headless Container in NAS Docker Stack

As a **developer**,
I want `obsidian-headless` running as a Docker container on NAS with access to the vault directory,
so that notes written by the MCP server are automatically synced to all devices via Obsidian Sync — without the PC being online.

**Acceptance Criteria:**

**Given** the community Docker image `belphemur/obsidian-headless-sync` (or current equivalent) is available
**When** the developer adds `obsidian-headless` service to `compose.nas.yaml`
**Then** the service is configured with:
  - Image: `belphemur/obsidian-headless-sync:latest` (or pinned version)
  - Volume: `{OBSIDIAN_VAULT_PATH}:/vault` (same path as MCP server uses)
  - Env vars: Obsidian Sync credentials (`OBSIDIAN_EMAIL`, `OBSIDIAN_PASSWORD`, `OBSIDIAN_VAULT_NAME`) — loaded from env file, NOT committed
  - `restart: unless-stopped`

**Given** `obsidian-headless` is running
**When** the MCP server writes a new `.md` file to `{OBSIDIAN_VAULT_PATH}/02-wiedza/`
**Then** `obsidian-headless` detects the file change and syncs it to Obsidian Sync servers
**And** the change appears on the developer's phone within 60 seconds (NFR13)

**Given** the Obsidian app is open on the developer's phone
**When** the sync completes
**Then** the updated note appears in Obsidian on phone without any manual action

**Given** the `obsidian-headless` container credentials are sensitive
**When** `infra/docker/obsidian_headless.env.example` is committed
**Then** it contains `OBSIDIAN_EMAIL=<your-email>` placeholders, not real values
**And** `infra/docker/obsidian_headless.env` is listed in `.gitignore`

**Technical notes:**
- Official `obsidian-headless` CLI was released in February 2026 — verify current Docker image availability before implementation
- Fallback: if `obsidian-headless` Docker image is unavailable, evaluate running directly on NAS via QNAP Container Station — document decision in `docs/adr/adr-015-obsidian-sync-strategy.md`
- Obsidian Sync subscription valid until 2026-11-02 — sufficient for MVP validation

### Story 40.2: Claude Custom Connector Configuration

As a **user**,
I want Claude's mobile app configured with a Custom Connector pointing to the MCP server,
so that Claude on my phone can invoke Lenie and Obsidian tools in a normal conversation.

**Acceptance Criteria:**

**Given** the MCP server is running (Epics 35–38) and Cloudflare infrastructure is set up (Epic 39)
**When** the developer opens Claude.ai → Settings → Integrations → Add Custom Connector
**Then** the connector is created with:
  - Name: `Lenie MCP`
  - URL: the Cloudflare connector URL from Epic 39 (Story 39-3)
  - Authentication: OAuth via Cloudflare MCP Portal

**Given** the Custom Connector is configured
**When** the developer opens a new Claude conversation on mobile and asks "What tools do you have from Lenie?"
**Then** Claude lists the available tools: `lenie_unreviewed_articles`, `lenie_get_article`, `lenie_search`, `lenie_delete_article`, `obsidian_read_note`, `obsidian_write_note`, `obsidian_list_notes`, `obsidian_delete_note`, `obsidian_note_history`

**Given** the Custom Connector is active
**When** Claude invokes `lenie_unreviewed_articles` in a conversation
**Then** it returns results from the actual NAS PostgreSQL database

**Given** the NAS or MCP server is offline
**When** Claude tries to invoke an MCP tool
**Then** Claude receives a connection error and communicates it to the user in natural language

**Technical notes:**
- Capture connector setup steps in `infra/cloudflare/README.md` as a one-time setup guide
- Test from both mobile (iOS/Android) and claude.ai desktop web

### Story 40.3: End-to-End Acceptance Test — MVP Gate

As a **developer**,
I want to validate the complete mobile knowledge workflow end-to-end,
so that I can confirm the MVP gate is met before declaring Sprint 14 done.

**Acceptance Criteria:**

**MVP Gate (must pass for Sprint 14 to be DONE):**

**Given** Claude is open on mobile with the Lenie MCP Custom Connector active
**When** the user asks "Pokaż mi nieprzejrzane artykuły"
**Then** Claude returns a list of unreviewed articles from the Lenie PostgreSQL database on NAS

**Given** an article is selected from the list
**When** the user asks "Pobierz treść tego artykułu"
**Then** Claude retrieves and displays the full article content

**Given** the article content is shown
**When** the user asks Claude to create an Obsidian note summarizing the article
**Then** Claude invokes `obsidian_write_note` with the note path and content
**And** the note file appears in the vault on NAS
**And** within 60 seconds, the note appears in Obsidian on the developer's phone

**Given** the note was written
**When** the user marks the article as reviewed (`mark_as_reviewed=True`)
**Then** the article's `reviewed_at` is set in the database
**And** the article no longer appears in the `lenie_unreviewed_articles` list

**Given** the above flow completed successfully
**When** the developer checks `obsidian_note_versions` in PostgreSQL
**Then** a version record exists with `content_after` matching the written note and `user_prompt` recorded

**Non-functional validation:**
- NFR5 (path safety): attempt `obsidian_write_note(note_path="../../etc/cron.d/hack")` — verify `note_path_invalid` error
- NFR9 (no overwrite without version): stop PostgreSQL, attempt `obsidian_write_note` — verify file is NOT written and `version_save_failed` error returned
- NFR13 (sync speed): confirm note appears on phone within 60 seconds

**Acceptance outcome:**
- PASS: All MVP gate criteria met in a real mobile session
- PARTIAL: Core flow works but one non-functional check fails — document as known issue
- FAIL: Core flow does not work — block Sprint 14 completion, diagnose root cause

**Technical notes:**
- Run acceptance test on actual phone using Claude iOS or Android app
- Document test run result in `_bmad-output/planning-artifacts/implementation-readiness-report-sprint14-mcp.md`
- This story has no code to write — it is a manual test and documentation task
- Failures in non-functional checks (path safety, version protection) must be fixed before PASS
