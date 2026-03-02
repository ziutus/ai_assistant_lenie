---
stepsCompleted:
  - step-01-validate-prerequisites
  - step-02-design-epics
  - step-03-create-stories
  - step-04-final-validation
status: complete
completedAt: '2026-02-28'
inputDocuments:
  - _bmad-output/planning-artifacts/prd.md
  - _bmad-output/planning-artifacts/prd-validation-report.md
  - _bmad-output/planning-artifacts/architecture.md
---

# lenie-server-2025 - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for the Lenie Slack Bot, decomposing the requirements from the PRD into implementable stories. Architecture document covers infrastructure (Sprint 4), not the Slack Bot — PRD Technical Context section serves as the architectural reference.

## Requirements Inventory

### Functional Requirements

FR1: User can add a URL to the knowledge base by providing the link via Slack
FR2: User can check whether a specific URL already exists in the knowledge base
FR3: User can retrieve detailed information about a document by its ID (type, status, title, date added)
FR4: User can query the current backend version and build timestamp
FR5: User can query the total document count in the knowledge base, broken down by document type
FR6: User can invoke bot capabilities via slash commands (`/lenie-version`, `/lenie-count`, `/lenie-check`, `/lenie-add`, `/lenie-info`)
FR7: Bot responds to slash commands with formatted text messages in the same Slack channel
FR8: User can invoke the same capabilities by sending text commands in a direct message to the bot
FR9: Bot parses DM text to identify the intended command and parameters
FR10: User can invoke bot capabilities by mentioning the bot on any channel (`@Lenie version`)
FR11: Bot responds to app mentions in the same channel thread
FR12: User can interact with the bot using natural language instead of structured commands
FR13: Bot interprets user intent via LLM and maps it to the appropriate backend API call
FR14: User can perform semantic search across the knowledge base via natural language query
FR15: Bot can periodically check backend health (API reachability, database connectivity)
FR16: Bot can send unprompted messages to the user when a health check fails
FR17: Bot does not send repeated alerts for the same ongoing failure (alert deduplication)
FR18: Bot displays user-friendly error messages when backend is unreachable (no stack traces, actionable suggestions)
FR19: Bot remains connected to Slack and responsive even when backend is down
FR20: Bot communicates specific failure reasons (timeout, HTTP error, invalid response) in plain language
FR21: Developer can deploy the bot as an optional Docker container using Compose profiles (`--profile slack`)
FR22: Developer can configure Slack tokens and backend URL via secret manager (Vault for Docker/NAS, SSM for AWS)
FR23: Developer can set up the Slack App using a manifest file included in the repository
FR24: Bot posts a startup confirmation message to a designated Slack channel upon successful connection
FR25: Developer can follow a step-by-step README to set up the bot from scratch (Slack workspace creation, App setup, token configuration, Docker launch)

### NonFunctional Requirements

NFR1: Bot responds to slash commands within 3 seconds (excluding backend API latency)
NFR2: Bot establishes Socket Mode connection within 10 seconds of container startup
NFR3: API client uses 5-second timeout for all backend HTTP calls — no hanging requests
NFR4: Zero secrets (Slack tokens, API keys) hardcoded in source code or Docker images
NFR5: All secrets retrieved from secret manager at runtime (Vault for Docker/NAS, SSM for AWS)
NFR6: Bot logs never contain secret values, tokens, or API keys (even at DEBUG level)
NFR7: Backend API key transmitted via `x-api-key` header, never as URL parameter
NFR8: Bot communicates with backend exclusively via HTTP REST API — zero code-level dependencies on `backend/`
NFR9: Bot tolerates backend API response format changes gracefully (logs warning, returns user-friendly error instead of crashing)
NFR10: Slack Bolt SDK version pinned in `pyproject.toml` to prevent breaking changes from automatic updates
NFR11: Code passes `ruff check` with zero warnings (line-length=120, consistent with backend)
NFR12: All public functions have type hints
NFR13: `api_client.py` and command handlers have unit tests with >80% coverage
NFR14: Clear module separation: Slack interaction logic (`commands.py`) decoupled from HTTP client (`api_client.py`)
NFR15: JSON structured logging from day one (`python-json-logger`)
NFR16: Bot process remains running and connected to Slack when backend is unreachable
NFR17: Slack Bolt SDK auto-reconnect handles transient Socket Mode disconnections without manual intervention
NFR18: Bot does not crash on malformed user input (invalid URL, missing ID, empty command arguments)

### Additional Requirements

- New top-level directory `slack_bot/` with `Dockerfile`, `pyproject.toml`, `src/`, `tests/unit/`
- Docker Compose profile `slack` in `infra/docker/compose.yaml` — started with `docker compose --profile slack up -d`
- Slack App manifest YAML in repo (`slack_bot/slack-app-manifest.yaml`) for automated App configuration
- Secrets via config_loader pattern (Vault for Docker/NAS, SSM for AWS)
- Module separation: `commands.py` (Slack handlers) vs `api_client.py` (HTTP client) vs `config.py` (configuration)
- Startup confirmation message posted to designated Slack channel
- JSON structured logging to stdout (Docker logs collection)
- Backend base URL configurable via `LENIE_API_URL` environment variable
- All API calls use `x-api-key` header for authentication
- 5-second HTTP timeout on all backend calls
- No architecture document exists for Slack Bot — PRD Technical Context section serves as reference

### FR Coverage Map

| FR | Epic | Description |
|----|------|-------------|
| FR1 | Epic 21 | Add URL via Slack |
| FR2 | Epic 21 | Check URL existence |
| FR3 | Epic 21 | Get document info by ID |
| FR4 | Epic 21 | Query backend version |
| FR5 | Epic 21 | Query document count by type |
| FR6 | Epic 21 | Invoke via slash commands |
| FR7 | Epic 21 | Formatted responses in channel |
| FR8 | Epic 22 | DM text commands |
| FR9 | Epic 22 | DM text parsing |
| FR10 | Epic 23 | App mentions on channels |
| FR11 | Epic 23 | Thread responses to mentions |
| FR12 | Epic 24 | Natural language interaction |
| FR13 | Epic 24 | LLM intent mapping to API calls |
| FR14 | Epic 24 | Semantic search via natural language |
| FR15 | Epic 25 | Periodic health checks |
| FR16 | Epic 25 | Proactive failure alerts |
| FR17 | Epic 25 | Alert deduplication |
| FR18 | Epic 21 | User-friendly error messages |
| FR19 | Epic 21 | Stay connected when backend down |
| FR20 | Epic 21 | Specific failure reasons in plain language |
| FR21 | Epic 21 | Docker Compose profile deployment |
| FR22 | Epic 21 | Secrets via Vault/SSM |
| FR23 | Epic 21 | Slack App manifest in repo |
| FR24 | Epic 21 | Startup confirmation message |
| FR25 | Epic 21 | Step-by-step setup README |

**Coverage: 25/25 FRs — 100%**

## Epic List

### Epic 21: Slack Bot MVP — Slash Commands (Sprint 7)
User can add links, check duplicates, query system status, and get document info via 5 Slack slash commands. Bot runs as an optional Docker container with full error handling, secrets management, and setup documentation.
**FRs covered:** FR1, FR2, FR3, FR4, FR5, FR6, FR7, FR18, FR19, FR20, FR21, FR22, FR23, FR24, FR25
**NFRs covered:** NFR1-NFR18 (all — quality foundation from first epic)

### Epic 22: Slack Bot Stabilization & DM Commands (Sprint 8)
Deploy Slack Bot MVP to NAS, verify end-to-end on real environment, fix any integration issues, then add simplified DM text commands (without conversational state). Deployment-first approach decided during [Epic 21 retrospective](../implementation-artifacts/epic-21-retro-2026-03-02.md).
**FRs covered:** FR8, FR9
**Builds on:** Epic 21

### Epic 23: Channel App Mentions (Sprint 8)
User can mention the bot on any channel (`@Lenie version`) and get a response in a thread. Same command set as slash commands and DMs.
**FRs covered:** FR10, FR11
**Builds on:** Epic 21, Epic 22

### Epic 24: Conversational LLM Intelligence (Sprint 8)
User interacts with the bot using natural language ("how many articles about Kubernetes?"). Bot interprets intent via LLM and maps to appropriate API call. Includes semantic search via `/website_similar`.
**FRs covered:** FR12, FR13, FR14
**Builds on:** Epic 21-23

### Epic 25: Proactive Health Monitoring (Sprint 8)
Bot periodically checks backend health and proactively alerts the user via DM when failures are detected. Alert deduplication prevents notification spam.
**FRs covered:** FR15, FR16, FR17
**Builds on:** Epic 21

---

## Epic 21: Slack Bot MVP — Slash Commands

User can add links, check duplicates, query system status, and get document info via 5 Slack slash commands. Bot runs as an optional Docker container with full error handling, secrets management, and setup documentation.

### Story 21.1: Project Scaffolding & Slack Connection

As a **developer**,
I want a `slack_bot/` project with Docker container that connects to Slack via Socket Mode,
So that I have a running bot foundation to build commands on.

**Acceptance Criteria:**

**Given** Docker Compose file has a `slack` profile with the bot service
**When** developer runs `docker compose --profile slack up -d`
**Then** the bot container starts and connects to Slack via Socket Mode within 10 seconds

**Given** the bot successfully connects to Slack
**When** connection is established
**Then** bot posts a startup confirmation message to a designated channel with version info

**Given** Slack tokens are stored in Vault (or SSM/env)
**When** the bot starts
**Then** it retrieves `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, and `STALKER_API_KEY` from the configured secret backend

**Given** the bot is running
**When** inspecting source code and Docker image
**Then** zero secrets are hardcoded and logs never contain token values

**Covers:** FR21, FR22, FR24 | NFR2, NFR4-NFR7, NFR10-NFR11, NFR14-NFR15

### Story 21.2: API Client for Backend Communication

As a **developer**,
I want an HTTP client module that calls Lenie backend REST API endpoints,
So that slash commands can retrieve and send data to the knowledge base.

**Acceptance Criteria:**

**Given** backend is running at `LENIE_API_URL`
**When** `api_client.get_version()` is called
**Then** it sends `GET /version` and returns parsed version data

**Given** backend is running
**When** `api_client.add_url("https://example.com")` is called
**Then** it sends `POST /url_add` with `x-api-key` header and URL payload

**Given** backend is unreachable (connection timeout)
**When** any API method is called
**Then** it raises a typed exception with clear error message (not raw stack trace)

**Given** backend returns HTTP 500
**When** any API method is called
**Then** it raises an exception with status code and response body for logging

**Given** unit test suite runs
**When** `pytest tests/unit/test_api_client.py` executes
**Then** all API methods are tested with mocked HTTP (no real backend needed), coverage >80%

**Covers:** NFR3, NFR7-NFR9, NFR13-NFR14

### Story 21.3: System Information Slash Commands

As a **user**,
I want to type `/lenie-version` and `/lenie-count` in Slack,
So that I can check system status quickly without opening the web UI.

**Acceptance Criteria:**

**Given** the bot is connected and backend is running
**When** user types `/lenie-version`
**Then** bot responds with backend version and build timestamp in the same channel within 3 seconds

**Given** the bot is connected and backend is running
**When** user types `/lenie-count`
**Then** bot responds with total document count and breakdown by type (webpage, youtube, link, etc.)

**Given** the backend is unreachable
**When** user types `/lenie-version` or `/lenie-count`
**Then** bot responds with user-friendly error message: "Backend unreachable (connection timeout). Check if lenie-ai-server is running."

**Given** the bot is connected
**When** backend returns unexpected response format
**Then** bot logs a warning and responds with "Unexpected response from backend" (no crash)

**Covers:** FR4, FR5, FR6 (partial), FR7, FR18-FR20 | NFR1, NFR16

### Story 21.4: Content Management Slash Commands

As a **user**,
I want to add links, check for duplicates, and get document details via Slack,
So that I can manage my knowledge base from mobile without opening the web UI.

**Acceptance Criteria:**

**Given** the bot is connected and backend is running
**When** user types `/lenie-add https://example.com/article`
**Then** bot calls `POST /url_add` and responds with "Added to knowledge base (ID: X). Type: link."

**Given** the URL already exists in the knowledge base
**When** user types `/lenie-check https://example.com/article`
**Then** bot responds with "Found in database (ID: X). Type: Y. Status: Z. Added: DATE."

**Given** the URL does not exist in the knowledge base
**When** user types `/lenie-check https://example.com/new`
**Then** bot responds with "Not found in database."

**Given** a document with ID 1234 exists
**When** user types `/lenie-info 1234`
**Then** bot responds with document type, status, title, and date added

**Given** user provides invalid input
**When** user types `/lenie-add` (no URL) or `/lenie-info abc` (non-numeric)
**Then** bot responds with usage hint: "Usage: `/lenie-add <url>`" (no crash)

**Given** backend is unreachable
**When** user types any content management command
**Then** bot responds with specific failure reason in plain language

**Covers:** FR1, FR2, FR3, FR6 (remaining), FR18-FR20 | NFR1, NFR16, NFR18

### Story 21.5: Slack App Manifest & Setup Documentation

As a **developer**,
I want a Slack App manifest and step-by-step README,
So that I can set up the bot from scratch in under 15 minutes.

**Acceptance Criteria:**

**Given** a developer has a free Slack workspace
**When** they import `slack-app-manifest.yaml` at api.slack.com
**Then** the Slack App is created with correct permissions (slash commands, Socket Mode, bot scopes)

**Given** the README exists
**When** a developer follows it step-by-step
**Then** they can go from zero to working bot: create workspace, create App, configure tokens, run `docker compose --profile slack up -d`, verify with `/lenie-version`

**Given** Slack tokens are classified as secrets
**When** reviewing `vars-classification.yaml`
**Then** `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN` are listed with `classification: secret` and appropriate backend definitions

**Covers:** FR23, FR25 | NFR12

---

## Epic 22: Slack Bot Stabilization & DM Commands

Deploy Slack Bot MVP to NAS, verify end-to-end on real environment, fix any integration issues discovered during deployment, then add simplified DM text commands. Deployment-first approach decided during [Epic 21 retrospective](../implementation-artifacts/epic-21-retro-2026-03-02.md). Conversational state (bare URL detection with confirmation prompt) removed from scope — deferred to future epic if needed.

### Story 22.1: NAS Deployment & End-to-End Verification

As a **developer**,
I want to deploy the Slack Bot to NAS and verify all 5 slash commands work end-to-end,
So that I have confidence the MVP works on a real environment before building new features.

**Acceptance Criteria:**

**Given** the NAS has Docker and the Lenie backend running
**When** developer runs `docker compose --profile slack up -d` on NAS
**Then** the bot container builds, starts, and connects to Slack via Socket Mode

**Given** the bot is running on NAS
**When** bot connects to Slack
**Then** startup confirmation message appears in the designated Slack channel

**Given** the bot is running on NAS with real backend
**When** user types `/lenie-version` in Slack
**Then** bot responds with actual backend version and build timestamp

**Given** the bot is running on NAS with real backend
**When** user types `/lenie-count` in Slack
**Then** bot responds with real document count and per-type breakdown

**Given** the bot is running on NAS with real backend
**When** user types `/lenie-add <url>`, `/lenie-check <url>`, `/lenie-info <id>` in Slack
**Then** all 3 content management commands work correctly with real data

**Given** deployment procedure is verified
**When** developer documents the process
**Then** a repeatable deployment procedure exists (git pull, build, up, verify)

**Covers:** FR21, FR24 | NFR2, NFR5, NFR8

### Story 22.2: Backend API Response Fixes (Conditional)

As a **developer**,
I want to fix any API response format mismatches discovered during NAS deployment,
So that the Slack Bot receives the exact response format it expects from all backend endpoints.

**Acceptance Criteria:**

**Given** NAS deployment revealed API response mismatches
**When** developer fixes the backend response format or Slack Bot parser
**Then** all 5 slash commands work correctly with real backend responses

**Given** NAS deployment revealed no issues
**When** this story is evaluated
**Then** story is marked as skipped (no work needed)

**Note:** This story may be empty if Story 22-1 deployment passes cleanly. Reserved as placeholder for integration fixes.

**Covers:** NFR9

### Story 22.3: DM Text Command Parsing (Simplified)

As a **user**,
I want to send commands as plain messages in a DM with the bot (e.g., "version", "add https://..."),
So that I can interact without remembering slash command syntax.

**Acceptance Criteria:**

**Given** the bot is connected and user is in a DM with it
**When** user sends "version"
**Then** bot responds with the same version info as `/lenie-version`

**Given** the bot is in a DM
**When** user sends "add https://example.com/article"
**Then** bot calls `POST /url_add` and responds with confirmation (same as `/lenie-add`)

**Given** the bot is in a DM
**When** user sends "check https://example.com/article"
**Then** bot responds with found/not-found (same as `/lenie-check`)

**Given** the bot is in a DM
**When** user sends "info 1234"
**Then** bot responds with document details (same as `/lenie-info`)

**Given** the bot is in a DM
**When** user sends unrecognized text (e.g., "hello" or "asdf")
**Then** bot responds with a help message listing available commands

**Covers:** FR8, FR9 | NFR1, NFR18

**Removed from original scope (Epic 21 retro decision):**
- ~~Bare URL detection with confirmation prompt ("Did you want to add this URL? Reply 'yes' to confirm.")~~ — requires conversational state management, deferred to future epic

---

## Epic 23: Channel App Mentions

User can mention the bot on any channel (`@Lenie version`) and get a response in a thread. Same command set as slash commands and DMs.

### Story 23.1: App Mention Event Handler & Thread Responses

As a **user**,
I want to mention `@Lenie` on any channel to invoke commands,
So that I can interact with the bot in team channels without switching to DM.

**Acceptance Criteria:**

**Given** the bot is added to a channel
**When** user posts `@Lenie version`
**Then** bot responds with version info **in a thread** under the mention message

**Given** the bot is mentioned on a channel
**When** user posts `@Lenie count`
**Then** bot responds with document count in a thread

**Given** the bot is mentioned on a channel
**When** user posts `@Lenie add https://example.com/article`
**Then** bot adds the URL and confirms in a thread

**Given** the bot is mentioned without a command
**When** user posts just `@Lenie`
**Then** bot responds in a thread with a help message listing available commands

**Given** the bot is mentioned on a channel it hasn't been added to
**When** the event arrives
**Then** bot handles gracefully (Slack shows "not in channel" — no bot crash)

**Covers:** FR10, FR11 | NFR1, NFR18

---

## Epic 24: Conversational LLM Intelligence

User interacts with the bot using natural language. Bot interprets intent via LLM and maps to API calls. Includes semantic search.

### Story 24.1: LLM Intent Parser

As a **user**,
I want to ask the bot questions in natural language ("how many articles do I have?"),
So that I don't need to remember specific command syntax.

**Acceptance Criteria:**

**Given** the bot is in a DM and LLM is configured
**When** user sends "how many articles do I have?"
**Then** LLM interprets intent as `count` command, bot responds with document count

**Given** the bot is in a DM
**When** user sends "do I already have this link? https://example.com"
**Then** LLM interprets intent as `check` command with URL, bot responds with found/not-found

**Given** the LLM service is unreachable
**When** user sends a natural language message
**Then** bot falls back to direct text parsing (Epic 22 logic) and responds or shows help

**Given** the LLM cannot determine intent
**When** user sends ambiguous message
**Then** bot responds: "I'm not sure what you mean. Available commands: version, count, check, add, info"

**Covers:** FR12, FR13 | NFR3, NFR9

### Story 24.2: Semantic Search via Natural Language

As a **user**,
I want to search my knowledge base with natural language ("articles about Kubernetes security"),
So that I can find relevant documents without knowing exact titles or IDs.

**Acceptance Criteria:**

**Given** the bot is connected and embeddings exist in the database
**When** user types `/lenie-search Kubernetes security`
**Then** bot calls `/website_similar` and responds with top results (title, type, score)

**Given** the bot is in a DM with LLM enabled
**When** user sends "find articles about pgvector performance"
**Then** LLM maps to search intent, bot returns similar documents

**Given** no similar documents are found
**When** user searches for an obscure topic
**Then** bot responds: "No similar documents found for 'topic'."

**Given** the query is empty
**When** user types `/lenie-search` without arguments
**Then** bot responds with usage hint

**Covers:** FR14 | NFR1, NFR18

---

## Epic 25: Proactive Health Monitoring

Bot periodically checks backend health and proactively alerts the user via DM when failures are detected. Alert deduplication prevents notification spam.

### Story 25.1: Scheduled Health Checks & Proactive Alerts

As a **user**,
I want the bot to alert me via DM when the backend goes down,
So that I learn about problems without manually checking.

**Acceptance Criteria:**

**Given** health monitoring is enabled and backend is running
**When** the health check runs every 5 minutes
**Then** no alerts are sent (system is healthy)

**Given** the backend becomes unreachable
**When** the next health check runs
**Then** bot sends a DM to the configured user: "Backend unreachable since HH:MM. Error: connection timeout."

**Given** the backend remains unreachable
**When** subsequent health checks continue to fail
**Then** bot does NOT send repeated alerts (deduplication active)

**Given** the backend comes back online after a failure
**When** the next health check succeeds
**Then** bot sends a recovery DM: "Backend recovered. Downtime: X minutes."

**Given** `HEALTH_CHECK_ENABLED=false`
**When** the bot starts
**Then** health monitoring is disabled, no background checks run

**Covers:** FR15, FR16, FR17 | NFR3, NFR16
