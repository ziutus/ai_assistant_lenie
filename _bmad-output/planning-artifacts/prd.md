---
stepsCompleted:
  - step-01-init
  - step-02-discovery
  - step-02b-vision
  - step-02c-executive-summary
  - step-03-success
  - step-04-journeys
  - step-05-domain
  - step-06-innovation
  - step-07-project-type
  - step-08-scoping
  - step-09-functional
  - step-10-nonfunctional
  - step-11-polish
  - step-12-complete
inputDocuments:
  - docs/index.md
  - docs/api-contracts-backend.md
  - docs/architecture-backend.md
  - docs/secrets-management.md
  - _bmad-output/planning-artifacts/archive/prd-sprint5-slack-bot-2026-03-04.md
documentCounts:
  briefs: 0
  research: 0
  brainstorming: 0
  projectDocs: 4
classification:
  projectType: api_backend
  domain: personal_ai_knowledge_management
  complexity: low
  projectContext: brownfield
  deploymentScope: script
workflowType: 'prd'
lastEdited: '2026-03-04'
---

# Product Requirements Document - lenie-server-2025

**Author:** Ziutus
**Date:** 2026-03-04

## Executive Summary

Notion Changelog is a lightweight proof-of-concept script that pushes the 10 most recently added documents from the Lenie knowledge base to a Notion workspace page. The goal is to evaluate whether Notion is a viable communication channel for keeping the team informed about new content — without requiring them to access the Lenie React UI.

This is a technical experiment, not a product feature. The script runs manually from the command line, reads directly from the PostgreSQL database, and writes to a Notion page via the Notion API. Success is measured by integration simplicity and maintainability — if the API connection is clean, reliable, and easy to keep running, Notion passes the test as a future communication channel.

Built as a standalone Python script in `backend/scripts/`, it reuses existing database access patterns and the unified config loader for secrets management (Notion API token stored in Vault/SSM/env, consistent with all other Lenie credentials).

### What Makes This Special

This is not about building a feature — it is about answering a question: "Is Notion a good fit for team communication in this project?" The smallest possible integration (one script, one API call, 10 items) gives the answer with minimal investment. If Notion works, it opens the door to richer integrations (automatic updates, bidirectional sync). If it doesn't, nothing was wasted.

## Project Classification

| Dimension | Value |
|-----------|-------|
| **Project Type** | API backend integration (Notion API consumer) |
| **Domain** | Personal AI knowledge management |
| **Complexity** | Low (single user, no regulatory requirements, PoC) |
| **Project Context** | Brownfield — new script added to existing backend |
| **Deployment Scope** | CLI script (manually triggered) |

## Success Criteria

### User Success

- Script executes with a single command (`python backend/scripts/notion_changelog.py`) and completes without errors
- Notion page displays the 10 most recently added documents with correct data: title, URL, document type, and date added
- Data in Notion is readable and useful — a team member glancing at the page understands what was recently added

### Business Success

- The experiment answers the question: "Is Notion a viable team communication channel for Lenie?"
- Decision made (yes/no) based on hands-on experience with the API, not speculation
- Minimal time investment — PoC built and evaluated within a single work session

### Technical Success

- Small script — compact codebase, easy to read and modify
- Configuration limited to 2 variables in Vault: `NOTION_API_TOKEN` and `NOTION_PAGE_ID`
- No new heavyweight dependencies — only `notion-client` (official Notion SDK)
- Reuses existing patterns: `config_loader` for secrets, direct PostgreSQL access for data

### Measurable Outcomes

- Script runs end-to-end with exit code 0
- Notion page contains exactly 10 items with correct titles and URLs (verified manually)
- Total new dependencies: 1 (`notion-client`)
- Total new config variables: 2 (`NOTION_API_TOKEN`, `NOTION_PAGE_ID`)

## Product Scope

### MVP

1. Python script at `backend/scripts/notion_changelog.py`
2. Reads 10 most recently added documents from PostgreSQL (ordered by `created_at DESC`)
3. Writes/updates a Notion page with a formatted list: title, URL, type, date added
4. Uses `config_loader` for `NOTION_API_TOKEN` and `NOTION_PAGE_ID`
5. Single command execution, clear stdout output (success/failure)

### Growth Features (Post-MVP)

- To be decided after PoC evaluation — no commitments at this stage

### Vision (Future)

- To be decided based on PoC results — potential directions include automatic scheduling, richer content, bidirectional sync, or abandoning Notion entirely

## User Journeys

### Journey 1: "Team Update" — Pushing Changelog to Notion

**Persona:** Ziutus — sole developer and operator of the Lenie knowledge base.

**Opening Scene:** Ziutus has just finished an import session — 15 new links and articles added to the knowledge base over the past few days. His team has no idea these resources exist because they don't use the React UI.

**Rising Action:** Ziutus opens a terminal and runs `python backend/scripts/notion_changelog.py`. The script connects to PostgreSQL, fetches the 10 most recently added documents, and calls the Notion API to update the designated page.

**Climax:** Within seconds, stdout confirms: "Updated Notion page with 10 items. Page URL: https://notion.so/..." Ziutus clicks the link — the Notion page shows a clean bulleted list: title, URL, type, and date for each item. His colleagues can see it immediately.

**Resolution:** The team now has a living page showing what's new in the knowledge base. Ziutus decides whether to mention it in Slack or just let people discover it. The whole operation took 5 seconds and one command.

### Journey 2: "Something Went Wrong" — Error Handling

**Persona:** Ziutus — running the script after a configuration change.

**Opening Scene:** Ziutus rotated the Notion API token in Vault but forgot to update one environment. He runs the script.

**Rising Action:** The script loads config via `config_loader`, gets the token, and attempts to connect to Notion API. The API returns 401 Unauthorized.

**Climax:** The script prints a clear error: "ERROR: Notion API authentication failed (401). Check NOTION_API_TOKEN in your secret backend." No stack trace, no crash — just an actionable message. Exit code 1.

**Resolution:** Ziutus checks Vault, spots the stale token, updates it, reruns the script. It works. Total debugging time: 30 seconds thanks to a clear error message.

### Journey Requirements Summary

| Journey | Capabilities Required |
|---------|----------------------|
| Team Update | PostgreSQL query (10 latest docs), Notion API page update, bulleted list formatting, stdout success confirmation |
| Error Handling | Config loader integration, Notion API error detection, user-friendly error messages, non-zero exit code on failure |

## Technical Context

### Architectural Position

Standalone Python script in `backend/scripts/` — not part of the Flask API. Reads directly from PostgreSQL, writes to Notion API. Zero coupling with Flask server; can run independently when database is accessible.

### Data Flow

```
PostgreSQL (web_documents table)
  ↓ SELECT id, url, title, document_type, created_at
  ↓ ORDER BY created_at DESC LIMIT 10
  ↓
notion_changelog.py
  ↓ notion-client SDK
  ↓
Notion Page (bulleted list)
```

### Database Query

Single SQL query against `web_documents` table — no ORM, no abstraction layer. Direct `psycopg2` connection using credentials from `config_loader`.

### Notion API Integration

- **SDK**: `notion-client` (official Python SDK by Notion)
- **Auth**: Internal Integration token (Bearer), stored as `NOTION_API_TOKEN`
- **Operation**: Replace page content with bulleted list (Notion Block API)
- **Target**: Single page identified by `NOTION_PAGE_ID`

### Secrets Management

Two new variables added to existing secret backends:

| Variable | Type | Description |
|----------|------|-------------|
| `NOTION_API_TOKEN` | secret | Notion Internal Integration token |
| `NOTION_PAGE_ID` | config | Target Notion page ID |

Managed via `config_loader` — works with env, Vault, and AWS SSM backends without code changes.

### Implementation Considerations

- Script reuses `config_loader` from `unified-config-loader` package — same pattern as `backend/server.py` and `slack_bot/`
- No Flask dependency — runs standalone with `python backend/scripts/notion_changelog.py`
- Error handling: catch Notion API errors (401, 404, rate limit), print actionable message, exit with code 1
- Logging: simple print statements to stdout (PoC scope — no structured logging needed)

## Project Scoping & Risk Mitigation

### MVP Strategy

**Approach:** Problem-solving MVP — the smallest script that answers the question "does Notion work for us?"

**Resources:** Solo developer (Ziutus), one work session, zero infrastructure changes.

**MVP covers both User Journeys** (Team Update + Error Handling) via the 5-point scope defined in Product Scope section.

### Risk Mitigation Strategy

**Technical Risk — Notion API Changes:**
Notion API is versioned. The `notion-client` SDK pins to a specific API version. **Mitigation:** Pin SDK version in `pyproject.toml`. For a PoC, this is sufficient.

**Dependency Risk — Database Must Be Accessible:**
Script requires direct PostgreSQL access. If DB is down, script fails. **Mitigation:** Clear error message on connection failure. No retry logic needed for manual execution.

**Integration Risk — Notion Page Permissions:**
The Internal Integration must be explicitly connected to the target page. Forgetting this step causes 404 errors. **Mitigation:** Document the "Connect to integration" step in script's docstring/README comment.

## Functional Requirements

### Data Retrieval

- FR1: Script can retrieve the 10 most recently added documents from the PostgreSQL database
- FR2: Script can extract title, URL, document type, and date added for each retrieved document

### Notion Integration

- FR3: Script can authenticate with the Notion API using an Internal Integration token
- FR4: Script can update a designated Notion page with a bulleted list of retrieved documents
- FR5: Script can format each list item to display title, URL, type, and date added

### Configuration

- FR6: Script can load Notion credentials (`NOTION_API_TOKEN`, `NOTION_PAGE_ID`) via the unified config loader
- FR7: Script can load database credentials via the unified config loader

### Error Communication

- FR8: Script can display a clear, actionable error message when Notion API authentication fails
- FR9: Script can display a clear, actionable error message when database connection fails
- FR10: Script can display a clear, actionable error message when the target Notion page is not found or not shared with the integration
- FR11: Script can exit with code 0 on success and code 1 on any failure

### Execution

- FR12: User can run the script with a single command from the terminal

## Non-Functional Requirements

### Security

- NFR1: Zero secrets (Notion token, DB credentials) hardcoded in source code
- NFR2: All secrets retrieved from config loader at runtime (env, Vault, or SSM)
- NFR3: Script never prints secret values to stdout, even in error messages

### Integration

- NFR4: Script uses the official `notion-client` SDK with pinned version in `pyproject.toml`
- NFR5: Script tolerates Notion API rate limiting gracefully (clear error message, no crash)
- NFR6: Script handles database connection timeout with actionable error message

### Code Quality

- NFR7: Code passes `ruff check` with zero warnings (line-length=120, consistent with backend)
- NFR8: Script is self-contained — single file, no additional module creation needed

## Appendix: Notion Setup Checklist

1. Create Internal Integration at https://www.notion.so/my-integrations (name: `Lenie Changelog Bot`, capability: Read & Insert content)
2. Copy the Integration Token (`ntn_...`) → store as `NOTION_API_TOKEN` in secret backend
3. Create a new page in the target workspace (e.g., "Lenie — Co nowego")
4. On that page: click `...` → "Connect to" → select `Lenie Changelog Bot`
5. Copy Page ID from the URL → store as `NOTION_PAGE_ID` in secret backend
6. Add `notion-client` to `pyproject.toml` dependencies
7. Add `NOTION_API_TOKEN` and `NOTION_PAGE_ID` to `scripts/vars-classification.yaml`
