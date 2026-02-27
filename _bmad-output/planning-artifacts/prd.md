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
classification:
  projectType: chatbot_integration
  domain: personal_ai_knowledge_management
  complexity: low
  projectContext: brownfield
  deploymentScope: docker_nas_only
  modularity: docker_compose_profiles
inputDocuments:
  - docs/index.md
  - docs/api-contracts-backend.md
  - docs/architecture-backend.md
  - docs/architecture-infra.md
  - _bmad-output/planning-artifacts/archive/prd-sprint4-infra-consolidation-2026-02-27.md
workflowType: 'prd'
lastEdited: '2026-02-27'
---

# Product Requirements Document - lenie-server-2025

**Author:** Ziutus
**Date:** 2026-02-27

## Executive Summary

Lenie Slack Bot is an optional chatbot module for the Lenie-AI personal knowledge management system, providing a natural language interface to the existing REST API via Slack. It replaces the click-heavy Chrome Extension workflow with conversational interaction — users type messages instead of filling forms. Deployed exclusively on Docker/NAS (Socket Mode), it avoids AWS costs associated with persistent processes.

The project serves a dual purpose: (1) a practical interface upgrade enabling mobile-friendly, natural language interaction with the knowledge base, and (2) a structured learning project for Slack bot development, bot command design, and external API integration — skills directly transferable to professional work.

Built in five phases: slash commands (foundation), DM command-based (event subscriptions), app mentions (channel interactions), conversational LLM-powered DM (intent parsing via OpenAI), and proactive monitoring (health checks, alerting). Each phase delivers immediate value while teaching a distinct Slack API capability.

**Target vision:** A Slack bot that answers questions about the knowledge base ("how many articles about Kubernetes?"), adds links via simple message paste, reports system version and health, and proactively alerts when infrastructure problems occur — all from a Slack conversation, including mobile.

### What Makes This Special

Three values converge in one project: (1) **UX paradigm shift** — from form-based Chrome Extension to natural language chat, making the system accessible from any device with Slack; (2) **professional skill building** — practical, portfolio-ready experience with Slack Bolt SDK, bot architecture, command design, and API integration patterns; (3) **proactive system awareness** — the bot monitors infrastructure health and initiates contact when problems arise, transforming Slack from a query tool into an operations assistant.

The core insight: Slack is not "another UI" — it is the interface where the user already lives. Meeting the knowledge base where the user is (mobile, desktop, anywhere) removes the friction that makes Chrome Extension usage feel heavy.

## Project Classification

| Dimension | Value |
|-----------|-------|
| **Project Type** | Chatbot integration (Slack Bot as optional module) |
| **Domain** | Personal AI knowledge management |
| **Complexity** | Low (single user, no regulatory requirements, educational project) |
| **Project Context** | Brownfield — new component added to running system (19 REST endpoints, PostgreSQL + pgvector, Docker Compose) |
| **Deployment Scope** | Docker/NAS only (AWS excluded — Socket Mode requires persistent process) |
| **Modularity** | Docker Compose profiles (`--profile slack`); formal plugin architecture deferred to backlog |

## Success Criteria

### User Success

- User pastes a link in Slack and the bot confirms it was added to the knowledge base within 3 seconds
- User asks the bot a question (version, count, check link, document info) and gets an accurate response in a single message
- User can interact with the bot via all three Slack methods: slash commands, direct messages, and app mentions
- User can operate the bot from mobile (Slack mobile app) with zero functionality loss compared to desktop

### Business Success

- **Portfolio quality**: Code is clean, well-structured, documented, and presentable as a professional portfolio piece — this applies to the entire Lenie project, not just the Slack bot
- **Transferable skills**: Developer can replicate Slack bot integration patterns in a professional context without referring to tutorials
- **Learning milestones completed**: Each of the 5 phases teaches a distinct, demonstrable Slack API capability (slash commands, event subscriptions, app mentions, LLM integration, proactive messaging)

### Technical Success

- Bot connects to existing Lenie REST API endpoints (`/version`, `/website_list`, `/url_add`, `/website_get`, `/website_similar`) and returns correct data
- Bot runs as a separate Docker container using Docker Compose profiles (`--profile slack`)
- Slack Bolt SDK (Python) handles all three interaction modes (slash commands, DM events, app mention events) in a single codebase
- Socket Mode connection remains stable during normal NAS operation (auto-reconnect on transient network issues handled by Bolt SDK)
- Code follows Python best practices: type hints, clear module structure, separation of Slack handling from API client logic, ruff-clean

### Measurable Outcomes

- 5 slash commands operational: `/lenie-version`, `/lenie-count`, `/lenie-check`, `/lenie-add`, `/lenie-info`
- Same 5 commands available via DM and app mentions
- Zero hardcoded URLs or credentials in bot code (all via environment variables or secret manager)
- Code passes `ruff check` with zero warnings (line-length=120, consistent with backend)
- Bot responds to commands in under 3 seconds (network latency to backend API excluded)

## Product Scope

### MVP — Phase 1 (Slash Commands)

1. Create Slack workspace (free plan) and Slack App with Bot user
2. Implement Slack Bolt SDK (Python) with Socket Mode
3. Implement 5 slash commands calling existing REST API:
   - `/lenie-version` → `GET /version`
   - `/lenie-count` → `GET /website_list` (count only)
   - `/lenie-check <url>` → `GET /website_list` (search by URL)
   - `/lenie-add <url>` → `POST /url_add`
   - `/lenie-info <id>` → `GET /website_get`
4. Docker container with `Dockerfile`, added to `compose.yaml` under `slack` profile
5. Documentation: setup guide, environment variables, Slack App configuration steps

### Growth Features (Post-MVP)

- **Phase 2: DM command-based** — Event subscriptions for direct messages, same 5 commands via text parsing
- **Phase 3: App mentions** — `@Lenie version` on channels, same command set
- **Phase 4: Conversational LLM** — Natural language intent parsing via OpenAI ("how many articles about Kubernetes?"), semantic search via `/website_similar`

### Vision (Future)

- **Phase 5: Proactive monitoring** — Scheduled health checks (database, backend, SQS queue), bot initiates DM on failures (nice-to-have)
- **Formal plugin architecture** — Modular system where Slack, RSS, MCP server are optional plugins with shared configuration
- **HTTP Mode + Lambda** — Alternative deployment for AWS (if cost-justified in the future)

## User Journeys

### Journey 1: "Found an interesting link" — Adding Content via Slack

**Persona:** Ziutus — sole developer and user, browsing news on mobile during commute.

**Opening Scene:** Ziutus is on a tram, scrolling Twitter on his phone. He spots an article about new pgvector features in PostgreSQL 18. With Chrome Extension, he'd need to: open the link in browser, click extension icon, fill the form, submit. Too much friction on mobile.

**Rising Action:** Ziutus opens Slack on his phone, pastes the URL into a DM with @Lenie, and types `/lenie-add https://example.com/pgvector-18-features`. The bot receives the command, calls `POST /url_add` on the backend, and waits for confirmation.

**Climax:** Within 2 seconds, the bot responds: "Added to knowledge base (ID: 1847). Type: link. Title auto-detected: 'What's New in pgvector 0.8.0'." Ziutus smiles — done. One message, no forms, no popups.

**Resolution:** The link is in the processing pipeline. Later, when Ziutus is at his desk, he can open the React UI to review, edit metadata, or trigger embedding generation. The Slack bot handled the capture — the heavy lifting happens elsewhere.

### Journey 2: "Do I already have this?" — Checking for Duplicates

**Persona:** Ziutus — reviewing shared links from a colleague.

**Opening Scene:** A friend sends Ziutus a link to an AWS re:Invent talk. Ziutus thinks "I might have added this last month" but doesn't want to open the React UI just to check.

**Rising Action:** Ziutus types `/lenie-check https://youtube.com/watch?v=abc123` in Slack.

**Climax:** Bot responds: "Found in database (ID: 1203). Type: youtube. Status: EMBEDDING_EXIST. Added: 2026-01-15." — Ziutus already has it, fully processed with embeddings.

**Resolution:** No duplicate added, no wasted processing. If the bot had responded "Not found in database," Ziutus would immediately follow up with `/lenie-add` to capture it.

### Journey 3: "System Status Check" — Quick Health Query

**Persona:** Ziutus — starting his work session, wants to know the system state.

**Opening Scene:** Ziutus opens his laptop in the morning. Before diving into development, he wants a quick pulse check on Lenie.

**Rising Action:** In Slack, he types `/lenie-version` and `/lenie-count`.

**Climax:** Bot responds: "Version: 0.3.13.0, Build: 2026-02-25T14:30:00Z" and "Database contains 1,847 documents (423 webpages, 312 youtube, 891 links, 221 other)."

**Resolution:** Ziutus knows the system is running the expected version and has a quick mental model of his knowledge base size. If the version were wrong or count unexpectedly low, he'd investigate immediately.

### Journey 4: "Something Went Wrong" — Error Handling

**Persona:** Ziutus — adding a link when backend is unreachable.

**Opening Scene:** Ziutus tries `/lenie-add https://example.com/article` from his phone. The NAS backend is down for maintenance — but Ziutus doesn't know that.

**Rising Action:** The bot attempts to call `POST /url_add` on the backend. The HTTP request times out after 5 seconds.

**Climax:** Bot responds: "Failed to add link. Backend unreachable (connection timeout). Check if lenie-ai-server container is running." — Clear error message, no cryptic stack trace, actionable suggestion.

**Resolution:** Ziutus knows exactly what happened and what to check. He saves the link in Slack (it's in the message history) and retries later. No data lost, no confusion.

### Journey 5: "First Time Setup" — Developer Onboarding

**Persona:** Ziutus — setting up the Slack bot for the first time.

**Opening Scene:** Ziutus has the Lenie Docker stack running on NAS. He wants to add the Slack bot module. He's never created a Slack App before.

**Rising Action:** Following the setup guide in the bot's README, Ziutus: (1) creates a free Slack workspace at slack.com, (2) creates a new Slack App at api.slack.com with the manifest from the repo, (3) copies the Bot Token and App-Level Token into the `.env` file, (4) runs `docker compose --profile slack up -d`.

**Climax:** The bot container starts, connects via Socket Mode, and posts in `#general`: "Lenie Bot connected. Version 0.3.13.0. Type `/lenie-version` to verify." Ziutus types the command and gets a response. It works.

**Resolution:** Setup took 15 minutes. The README covered every step. Ziutus has a working Slack bot connected to his knowledge base. The learning journey begins.

### Journey Requirements Summary

| Journey | Capabilities Required |
|---------|----------------------|
| Adding Content | `/lenie-add` slash command, `POST /url_add` API call, success/error response formatting |
| Checking Duplicates | `/lenie-check` slash command, `GET /website_list` with URL filter, result formatting |
| System Status | `/lenie-version` and `/lenie-count` slash commands, `GET /version` and `GET /website_list` API calls |
| Error Handling | HTTP timeout handling, user-friendly error messages, actionable suggestions, no data loss |
| First Time Setup | Slack App manifest in repo, Docker Compose profile, setup documentation, startup confirmation message |

The user journeys above define *what* the bot does. The following section defines *how* it integrates into the existing system.

## Technical Context

### Architectural Position

Slack Bot is an independent service communicating with the backend exclusively via HTTP REST API — zero code-level dependencies on `backend/`. Architecturally equivalent to Chrome Extension and React UI: a standalone API consumer.

### Repository Structure

New top-level directory `slack_bot/` — consistent with existing layout (`backend/`, `web_interface_react/`, `web_chrome_extension/`). Optional module, not embedded in the backend.

```
slack_bot/
├── Dockerfile
├── README.md
├── pyproject.toml
├── src/
│   ├── __init__.py
│   ├── main.py          # Entry point, Socket Mode connection
│   ├── commands.py       # Slash command handlers
│   ├── api_client.py     # HTTP client for Lenie REST API
│   └── config.py         # Configuration loading (Vault/SSM/env)
└── tests/
    └── unit/
```

### API Communication

Bot calls existing backend REST API endpoints over HTTP:

| Bot Command | Backend Endpoint | Method | Auth |
|-------------|-----------------|--------|------|
| `/lenie-version` | `/version` | GET | None |
| `/lenie-count` | `/website_list` | GET | `x-api-key` |
| `/lenie-check <url>` | `/website_list` | GET | `x-api-key` |
| `/lenie-add <url>` | `/url_add` | POST | `x-api-key` |
| `/lenie-info <id>` | `/website_get` | GET | `x-api-key` |

Backend base URL configurable via environment variable (e.g., `LENIE_API_URL=http://lenie-ai-server:5000`).

### Secrets Management

Slack tokens (Bot Token `xoxb-...`, App-Level Token `xapp-...`) stored in:
- **Docker/NAS:** HashiCorp Vault (consistent with B-63 migration)
- **AWS (future):** SSM Secrets Manager

Backend API key (`STALKER_API_KEY`) retrieved from the same secret backend.

### Logging

- **Format:** JSON structured logging from day one (e.g., `python-json-logger`)
- **Output:** stdout (Docker logs collects automatically)
- **Backend migration to JSON logging:** Deferred to backlog (separate cross-project change)

### Docker Deployment

```yaml
# In infra/docker/compose.yaml
services:
  lenie-ai-slack-bot:
    build: ../../slack_bot
    profiles: ["slack"]
    environment:
      - LENIE_API_URL=http://lenie-ai-server:5000
      - SECRETS_BACKEND=vault
    depends_on:
      - lenie-ai-server
```

Started with: `docker compose --profile slack up -d`

### Implementation Considerations

- **Slack Bolt SDK** (`slack-bolt`) handles Socket Mode, slash commands, events, and app mentions in a unified framework
- **Separation of concerns:** `commands.py` (Slack interaction) decoupled from `api_client.py` (HTTP calls) — testable independently, patterns reusable in professional context
- **Error handling:** All API calls wrapped with timeout (5s) and user-friendly error messages (no stack traces in Slack responses)
- **Portfolio quality:** Type hints, docstrings on public functions, ruff-clean code, comprehensive unit tests for `api_client.py` and command handlers

## Project Scoping & Risk Mitigation

### MVP Strategy

**Approach:** Problem-solving MVP — deliver the smallest useful bot that proves Slack integration works end-to-end. One slash command working reliably is more valuable than five commands half-working.

**Resources:** Solo developer (Ziutus), Python + Slack Bolt SDK knowledge, existing NAS with Docker stack running.

**MVP covers all 5 User Journeys** via Phase 1 capabilities defined in Product Scope. Post-MVP phases (2-5) are also defined in Product Scope — each phase is a separate backlog epic with its own acceptance criteria.

### Risk Mitigation Strategy

**Technical Risk — Slack App Configuration:**
First-time Slack App setup (permissions, OAuth scopes, Socket Mode toggle) can be confusing. **Mitigation:** Include a Slack App manifest YAML in the repo (`slack_bot/slack-app-manifest.yaml`) — this automates 90% of the configuration. Document the remaining manual steps with screenshots in README.

**Dependency Risk — Backend Must Be Running:**
Bot is useless when `lenie-ai-server` is down. On NAS, Docker containers may restart after power events. **Mitigation:** Bot handles backend unavailability gracefully — clear error message ("Backend unreachable"), no crash, auto-retry on next command. The bot itself stays connected to Slack regardless of backend state. `depends_on` in Docker Compose ensures correct startup order.

**Process Risk — Scope Creep Across Phases:**
5 phases is ambitious. Risk of starting Phase 2 before Phase 1 is solid. **Mitigation:** Each phase is a separate backlog epic. Phase 1 must pass all acceptance criteria (5 commands working, tests passing, documentation complete) before Phase 2 starts. No mixing phases.

## Functional Requirements

### Content Management

- FR1: User can add a URL to the knowledge base by providing the link via Slack
- FR2: User can check whether a specific URL already exists in the knowledge base
- FR3: User can retrieve detailed information about a document by its ID (type, status, title, date added)

### System Information

- FR4: User can query the current backend version and build timestamp
- FR5: User can query the total document count in the knowledge base, broken down by document type

### Slack Interaction — Slash Commands (Phase 1)

- FR6: User can invoke bot capabilities via slash commands (`/lenie-version`, `/lenie-count`, `/lenie-check`, `/lenie-add`, `/lenie-info`)
- FR7: Bot responds to slash commands with formatted text messages in the same Slack channel

### Slack Interaction — Direct Messages (Phase 2)

- FR8: User can invoke the same capabilities by sending text commands in a direct message to the bot
- FR9: Bot parses DM text to identify the intended command and parameters

### Slack Interaction — App Mentions (Phase 3)

- FR10: User can invoke bot capabilities by mentioning the bot on any channel (`@Lenie version`)
- FR11: Bot responds to app mentions in the same channel thread

### Conversational Intelligence (Phase 4)

- FR12: User can interact with the bot using natural language instead of structured commands
- FR13: Bot interprets user intent via LLM and maps it to the appropriate backend API call
- FR14: User can perform semantic search across the knowledge base via natural language query

### Proactive Monitoring (Phase 5 — Nice-to-Have)

- FR15: Bot can periodically check backend health (API reachability, database connectivity)
- FR16: Bot can send unprompted messages to the user when a health check fails
- FR17: Bot does not send repeated alerts for the same ongoing failure (alert deduplication)

### Error Communication

- FR18: Bot displays user-friendly error messages when backend is unreachable (no stack traces, actionable suggestions)
- FR19: Bot remains connected to Slack and responsive even when backend is down
- FR20: Bot communicates specific failure reasons (timeout, HTTP error, invalid response) in plain language

### Configuration & Deployment

- FR21: Developer can deploy the bot as an optional Docker container using Compose profiles (`--profile slack`)
- FR22: Developer can configure Slack tokens and backend URL via secret manager (Vault for Docker/NAS, SSM for AWS)
- FR23: Developer can set up the Slack App using a manifest file included in the repository
- FR24: Bot posts a startup confirmation message to a designated Slack channel upon successful connection

### Documentation

- FR25: Developer can follow a step-by-step README to set up the bot from scratch (Slack workspace creation, App setup, token configuration, Docker launch)

## Non-Functional Requirements

### Performance

- NFR1: Bot responds to slash commands within 3 seconds (excluding backend API latency)
- NFR2: Bot establishes Socket Mode connection within 10 seconds of container startup
- NFR3: API client uses 5-second timeout for all backend HTTP calls — no hanging requests

### Security

- NFR4: Zero secrets (Slack tokens, API keys) hardcoded in source code or Docker images
- NFR5: All secrets retrieved from secret manager at runtime (Vault for Docker/NAS, SSM for AWS)
- NFR6: Bot logs never contain secret values, tokens, or API keys (even at DEBUG level)
- NFR7: Backend API key transmitted via `x-api-key` header, never as URL parameter

### Integration

- NFR8: Bot communicates with backend exclusively via HTTP REST API — zero code-level dependencies on `backend/`
- NFR9: Bot tolerates backend API response format changes gracefully (logs warning, returns user-friendly error instead of crashing)
- NFR10: Slack Bolt SDK version pinned in `pyproject.toml` to prevent breaking changes from automatic updates

### Code Quality

- NFR11: Code passes `ruff check` with zero warnings (line-length=120, consistent with backend)
- NFR12: All public functions have type hints
- NFR13: `api_client.py` and command handlers have unit tests with >80% coverage
- NFR14: Clear module separation: Slack interaction logic (`commands.py`) decoupled from HTTP client (`api_client.py`)
- NFR15: JSON structured logging from day one (`python-json-logger`)

### Reliability

- NFR16: Bot process remains running and connected to Slack when backend is unreachable
- NFR17: Slack Bolt SDK auto-reconnect handles transient Socket Mode disconnections without manual intervention
- NFR18: Bot does not crash on malformed user input (invalid URL, missing ID, empty command arguments)
