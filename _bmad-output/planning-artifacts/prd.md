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
  - docs/adr/adr-005-remove-ai-ask-mcp-architecture.md
  - docs/CICD/NAS_Deployment.md
  - README.md
  - _bmad-output/planning-artifacts/architecture.md
documentCounts:
  briefs: 0
  research: 0
  brainstorming: 0
  projectDocs: 4
classification:
  projectType: api_backend
  domain: personal_ai_knowledge_management
  complexity: medium
  projectContext: brownfield
---

# Product Requirements Document - lenie-server-2025

**Author:** Ziutus
**Date:** 2026-04-10 (revised 2026-04-12 — addressed all validation warnings)

## Executive Summary

Lenie-AI is a personal knowledge management system that collects, processes, and stores web articles, YouTube transcriptions, and links in a PostgreSQL database with vector search capabilities. The system currently operates through a Flask REST API, React SPA, and Chrome/Kiwi browser extension, with Claude Code serving as the AI analysis layer via local MCP tools.

This PRD defines the next evolution: **exposing Lenie-AI and an Obsidian vault as a Remote MCP server on the NAS**, accessible from Claude's mobile client (claude.ai Custom Connector). The goal is to unlock the existing knowledge workflow — article review, note creation, knowledge consolidation — during short mobile sessions (5-15 minutes) that currently go unused: commuting, waiting with a child, or before getting out of bed.

The AWS ingestion layer (API Gateway → SQS → DynamoDB) remains unchanged as a reliable, always-available "mailbox" for capturing links from mobile browsers. DynamoDB-to-PostgreSQL synchronization continues as a separate concern, with improvements to reliability and automation in scope.

### What Makes This Special

This is not "mobile access to a database." It is **transferring an existing AI-assisted knowledge workflow from desktop to mobile** — the same workflow that today runs through Claude Code's `/obsidian-note` slash command. Claude proactively fetches new articles from Lenie, proposes Obsidian note updates with key points, and the user approves or adjusts. The interaction model is conversational and atomic: each 5-minute session produces concrete knowledge artifacts without requiring the user to manage files, navigate UIs, or remember where things are stored.

The core insight: the user's computer time is reserved for programming and high-value creative work. Knowledge management should happen during otherwise idle moments, driven by an AI that knows the knowledge base and can act on it autonomously.

## Project Classification

- **Project Type:** API backend (MCP server — protocol adapter between Claude and existing systems)
- **Domain:** Personal AI Knowledge Management
- **Complexity:** Medium (new protocol + security layer + file sync, but single user, known infrastructure)
- **Project Context:** Brownfield — extends existing NAS Docker stack (9 containers), Lenie backend, and Obsidian integration

## Success Criteria

### User Success

- User opens Claude on mobile, asks about new articles, and receives a list from Lenie within a single conversational turn
- User reviews an article summary and approves an Obsidian note update in under 5 minutes
- Updated note appears in Obsidian on all devices via Obsidian Sync
- The workflow feels like a natural conversation, not a technical operation

### Business Success (Personal Project)

- Used multiple times daily during otherwise idle moments (commute, waiting, morning routine)
- Knowledge base in Obsidian grows consistently without dedicating computer time to it
- Infrastructure maintenance stays within a few hours per month — and doubles as a learning opportunity (Cloudflare Tunnel, MCP protocol, Docker orchestration)
- DynamoDB sync reliability improves (currently manual, ad-hoc)

### Technical Success

- MVP validation: the end-to-end flow works — Claude on mobile reads from Lenie PostgreSQL and writes to Obsidian vault via Remote MCP server on NAS
- Detailed performance and reliability targets deferred to post-MVP evaluation

### Measurable Outcomes

- **MVP gate:** Claude on mobile successfully creates or updates one Obsidian note from a Lenie article, and the change propagates to all devices
- **Adoption signal:** user naturally reaches for the phone workflow instead of deferring knowledge work to computer time

## User Journeys

### Journey 1: Mobile Knowledge Worker — "10 minut w tramwaju"

**Ziutus** jedzie tramwajem po odprowadzeniu dziecka do przedszkola. Ma 10 minut i telefon w ręku.

**Opening:** Otwiera Claude'a na claude.ai. Pisze: "Pobierz mi najnowsze artykuły z Lenie, przejrzyjmy je razem."

**Rising Action:** Claude wywołuje `lenie_unreviewed_articles` i zwraca listę 6 najnowszych artykułów bez notatki Obsidian (z informacją o łącznej liczbie nieprzejrzanych). Ziutus wybiera jeden. Claude pobiera pełną treść przez `lenie_get_article`, wyświetla podsumowanie i notatkę użytkownika (co go zainteresowało). Ziutus czyta podsumowanie — kojarzy artykuł, bo wcześniej sam go oczyścił w `article_browser.py`.

**Climax:** Claude proponuje: "Dodałbym te 3 punkty do notatki `Kraje/Turcja/Polityka.md` i utworzył nową sekcję o sankcjach." Pokazuje propozycję zmian. Ziutus mówi "OK, ale zmień punkt 2 na..." Claude koryguje i zapisuje przez `obsidian_write_note` (system automatycznie wersjonuje poprzednią treść). Aktualizuje `reviewed_at` i `obsidian_note_paths` w bazie Lenie.

**Resolution:** Notatka Obsidian zaktualizowana, artykuł oznaczony. Obsidian Sync propaguje zmianę na wszystkie urządzenia (bez potrzeby włączonego PC). Cała operacja zajęła 4 minuty — zostaje czas na drugi artykuł.

**Edge case — artykuł za duży:** Ziutus mówi "ten jest za długi, przejdźmy do następnego." Artykuł nie jest oznaczany — wraca do puli automatycznie.

**Edge case — sprawdzenie historii zmian:** Następnego dnia Ziutus otwiera notatkę `Kraje/Turcja/Polityka.md` i widzi, że jakaś sekcja wygląda inaczej niż pamięta. Pyta Claude'a: "pokaż mi co ostatnio zmieniłeś w tej notatce". Claude wywołuje `obsidian_note_history` i pokazuje listę ostatnich zmian (data, prompt który wywołał zmianę, diff przed/po). Ziutus widzi że to jego własna instrukcja sprzed dwóch dni i spokojnie wraca do pracy. Transparency notes versioning daje zaufanie do AI workflow.

### Journey 2: Mobile Knowledge Worker — "Wieczór przy bajkach"

**Ziutus** siedzi z dzieckiem, które ogląda bajki. Ma 15 minut i nie chce być nieobecny, ale może korzystać z telefonu.

**Opening:** Otwiera Claude'a. "Co mam nowego w Lenie?"

**Rising Action:** Claude zwraca 6 nieprzejrzanych artykułów z rozmiarem. Ziutus przegląda podsumowania jedno po drugim. Dwa go interesują, trzy nie, jeden jest za duży.

**Climax:** Dla interesujących artykułów Claude proponuje aktualizacje notatek Obsidian (może aktualizować kilka notatek jednocześnie — np. artykuł o sankcjach wpływa na notatkę o Turcji i o UE). Ziutus zatwierdza propozycje z drobnymi korektami. Dla nieinteresujących mówi "usuń" — Claude kasuje artykuł z bazy Lenie przez `lenie_delete_article`. Za duży artykuł zostaje bez oznaczenia — wraca do puli.

**Resolution:** 2 notatki zaktualizowane, 3 artykuły usunięte, 1 odłożony. Baza wiedzy rośnie bez siadania do komputera.

### Journey 3: Infrastructure Operator — "Coś nie działa"

**Ziutus** otwiera Claude'a na telefonie, ale MCP nie odpowiada.

**Opening:** Claude wyświetla błąd połączenia z MCP serverem.

**Rising Action:** Ziutus sprawdza czy NAS jest online (ping, QNAP app). Jeśli NAS działa — problem z tunelem Cloudflare lub kontenerem MCP. Ziutus loguje się na NAS przez SSH lub QNAP app i restartuje kontener.

**Resolution:** MCP server wraca. To się zdarza rzadko (restart NAS, aktualizacja QTS). Akceptowalne w MVP — monitoring i alerty to Growth feature.

### Journey Requirements Summary

| Journey | Required MCP Tools | Infrastructure |
|---------|-------------------|----------------|
| 1 & 2 (Mobile Knowledge) | `lenie_unreviewed_articles`, `lenie_get_article`, `lenie_delete_article`, `lenie_search`, `obsidian_read_note`, `obsidian_write_note`, `obsidian_list_notes`, `obsidian_delete_note`, `obsidian_note_history` | MCP server, Cloudflare Tunnel, Obsidian vault sync, Claude Custom Connector |
| 3 (Operator) | — | SSH access to NAS, Docker CLI, monitoring (post-MVP) |

## Domain-Specific Requirements

### Security — MCP Server Access

The MCP server exposes read/write access to PostgreSQL (articles) and the Obsidian vault filesystem. Security layers:

1. **Network layer:** Cloudflare Tunnel — MCP server is never directly exposed to the internet. All traffic routed through Cloudflare's edge network.
2. **Authentication layer:** Cloudflare MCP Server Portal (Zero Trust) — OAuth-based authentication before traffic reaches the MCP server. Identity provider login required (e.g., Google). This is the sole authentication layer — Claude Custom Connector does not support additional auth headers beyond OAuth.

**Domain setup:** Dedicated low-cost domain (~3 EUR/year) managed entirely by Cloudflare DNS. Production domain `lenie-ai.eu` remains on AWS Route53 — zero impact on existing infrastructure.

### Data Integrity — Obsidian Vault

- MCP server has write access restricted to `02-wiedza/` directory only — no access to journal, templates, or other vault areas
- Single-user guarantee: no concurrent edits from multiple sources
- Delete operations on Lenie articles do not require confirmation
- Every write operation automatically versioned in `obsidian_note_versions` table (see MCP Server Specific Requirements)

### Obsidian Vault Synchronization

**Solution:** `obsidian-headless` (official Obsidian CLI, released Feb 2026) running as a Docker container on NAS, using existing Obsidian Sync subscription (Standard 1 GB plan, valid until 2026-11-02).

**Sync chain (no PC required):**
```
MCP server writes file on NAS
    → obsidian-headless container detects change
        → Obsidian Sync → phone + PC (seconds)
```

- No Syncthing needed — Obsidian Sync handles all device synchronization
- E2E encrypted, bidirectional, conflict resolution handled by Obsidian
- Community Docker image available: [obsidian-headless-sync-docker](https://github.com/Belphemur/obsidian-headless-sync-docker)

**Backlog (September 2026):** Evaluate whether to renew Obsidian Sync or migrate to Syncthing before subscription expires (2026-11-02).

### Infrastructure Dependencies

| Dependency | Failure Impact | MVP Mitigation |
|------------|---------------|----------------|
| NAS (QNAP) | MCP server unavailable | Accept downtime — personal project |
| Cloudflare Tunnel | MCP server unreachable | Tunnel auto-reconnects; manual restart if needed |
| Obsidian Sync | Notes not propagated | Independent of MCP — Obsidian handles retry |
| Claude Custom Connector | Cannot initiate workflow | No mitigation — depends on Anthropic |
| PostgreSQL on NAS | Articles unavailable | Already monitored via existing Docker healthchecks |

### Educational Value

Technologies to explore: Cloudflare ecosystem (DNS, Tunnel, Zero Trust, MCP Server Portals), MCP protocol (Python SDK), Docker orchestration on NAS, Obsidian headless sync.

Infrastructure maintenance budget: a few hours per month, treated as learning investment.

## MCP Server Specific Requirements

### Project-Type Overview

Remote MCP server deployed as a Docker container on NAS, exposing Lenie knowledge base and Obsidian vault to Claude mobile client via Cloudflare MCP Server Portal.

### API Documentation

This section is the canonical API contract for the MCP server. Downstream consumers (Claude Custom Connector, future MCP clients, integration tests) should reference these subsections:

| Concern | Subsection | Purpose |
|---------|------------|---------|
| **Tool catalog** | [MCP Tools Specification](#mcp-tools-specification) | All available tools with operation type, parameters, and return shape |
| **Data schemas** | [MCP Tools Specification](#mcp-tools-specification) returns + [Note Version History](#note-version-history-mvp) | Field-level structure of responses and persisted records |
| **Error contract** | [Error Handling](#error-handling) | Error codes, triggers, and user-facing message patterns |
| **Throughput & limits** | [Rate Limits & Concurrency](#rate-limits--concurrency) | Concurrency model and (lack of) rate limiting in MVP |
| **Wire format** | [Data Format](#data-format) | Encoding conventions for article lists, details, and notes |
| **Protocol** | [Implementation Considerations](#implementation-considerations) | MCP transport, SDK, integration points |

**API Versioning:** MVP exposes a single unbumped version. Breaking changes in tool signatures or error codes will be tracked via the MCP server's own version string (returned on connection handshake) starting in Phase 2. Until then, the Custom Connector is assumed to be in lockstep with server deployment.

**Stability contract:** Tool names, parameter names, and error codes documented in this section are the stable surface. Internal implementation details (table column names, Docker network names, container choices in NFRs) may change without API version bump.

### MCP Tools Specification

#### Lenie Tools (PostgreSQL)

| Tool | Operation | Returns |
|------|-----------|---------|
| `lenie_unreviewed_articles` | READ | List (default 6, newest first): title, source, size (KB), user note, date, total unreviewed count. Filter: `reviewed_at IS NULL` or `obsidian_note_paths = []`. Supports pagination and filters (source, type, date range). |
| `lenie_search` | READ | Search results matching keyword/phrase |
| `lenie_get_article` | READ | Full markdown content + metadata (title, date, source, language, user note, obsidian_note_paths) |
| `lenie_delete_article` | DELETE | Confirmation of deletion |

#### Obsidian Tools (Filesystem — restricted to `02-wiedza/`)

| Tool | Operation | Returns |
|------|-----------|---------|
| `obsidian_read_note` | READ | Full markdown content of a note |
| `obsidian_write_note` | CREATE/UPDATE | Writes file, saves version to `obsidian_note_versions` table before overwriting. Optional params: `article_id` (auto-links note path to article's `obsidian_note_paths`), `mark_as_reviewed` (sets `reviewed_at = NOW()` on the article — used when user confirms work on article is complete). |
| `obsidian_list_notes` | READ | List of notes in folder/subfolder |
| `obsidian_delete_note` | DELETE | Removes note file |
| `obsidian_note_history` | READ | List of past versions for a note (date, user prompt, diff before/after). Default limit 10, newest first. |

### Note Version History (MVP)

Table `obsidian_note_versions` — automatic versioning before every MCP write:

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL PK | |
| `note_path` | TEXT | Relative path within vault |
| `content_before` | TEXT | Content before change |
| `content_after` | TEXT | Content after change |
| `user_prompt` | TEXT | What user asked Claude to do |
| `article_id` | INTEGER FK (nullable) | Source Lenie article |
| `changed_by` | TEXT | `mcp_server` |
| `created_at` | TIMESTAMPTZ | Timestamp |

**Backlog:** Automated quality audit — Claude reviews recent changes to verify `content_after` correctly implements `user_prompt` without losing `content_before` data.

### Data Format

- Article lists: metadata + size in KB + user note (no full content)
- Article detail: full markdown content + all metadata in single response
- Obsidian notes: raw markdown

### Error Handling

MCP tools return structured errors with code, human-readable message, and optional details. Claude surfaces these to the user conversationally.

| Error Code | Trigger | User-Facing Message Pattern |
|------------|---------|------------------------------|
| `article_not_found` | `lenie_get_article` / `lenie_delete_article` with non-existent UUID | "Nie znalazłem artykułu o tym ID — możliwe że został wcześniej usunięty." |
| `note_not_found` | `obsidian_read_note` / `obsidian_note_history` with non-existent path | "Nie ma notatki pod tą ścieżką w `02-wiedza/`." |
| `note_path_invalid` | Path traversal attempt (`..`, absolute path, outside `02-wiedza/`) | "Ścieżka jest poza dozwolonym obszarem `02-wiedza/`." (operacja odrzucona, próba zalogowana) |
| `vault_write_failed` | Filesystem error during `obsidian_write_note` (permissions, disk full, sync conflict) | "Nie udało się zapisać notatki — sprawdź miejsce na dysku i status Obsidian Sync." |
| `database_unavailable` | PostgreSQL connection failure | "Baza Lenie jest niedostępna — sprawdź czy NAS i kontener `lenie-ai-db` działają." |
| `version_save_failed` | DB write to versioning store failed before note overwrite | "Wstrzymałem zapis notatki — nie mogłem zapisać wersji historycznej. Notatka nie została zmieniona." (NFR7 — no overwrite without version save) |

### Rate Limits & Concurrency

Single-user personal project — no rate limiting in MVP. Concurrent request handling delegated to MCP SDK and FastAPI defaults. Post-MVP consideration: if multiple Claude conversations run in parallel, evaluate need for per-tool semaphores around `obsidian_write_note` to prevent vault sync conflicts.

### Implementation Considerations

- MCP protocol: Python SDK (`mcp` package), JSON-RPC transport over SSE/streamable HTTP
- Database access: reuse existing `DocumentService` and `SearchService` (already decoupled from Flask)
- Filesystem access: restricted to vault path `{OBSIDIAN_VAULT_PATH}/02-wiedza/`
- Docker: new container in `compose.nas.yaml`, connects to existing `lenie-ai-db` on `lenie-net` network

## Project Scoping & Phased Development

### MVP Strategy & Philosophy

**MVP Approach:** Problem-solving MVP — validate that the mobile knowledge workflow (article review → Obsidian note creation) works end-to-end through MCP, before optimizing speed, reliability, or adding features.

**MVP Gate:** Claude on mobile successfully reads an article from Lenie, creates/updates an Obsidian note, and the change propagates to all devices via Obsidian Sync.

**Resource Requirements:** Single developer (Ziutus), estimated a few weekends of focused work. Technologies: Python (MCP SDK), Docker, Cloudflare (new), obsidian-headless (new).

### MVP Feature Set (Phase 1)

**Core User Journeys Supported:**
- Journey 1: "10 minut w tramwaju" — full flow
- Journey 2: "Wieczór przy bajkach" — full flow

**Must-Have Capabilities:**

| Component | What | Why essential |
|-----------|------|---------------|
| MCP Server | 10 tools (4 Lenie + 5 Obsidian + history reader, with review logic built into `obsidian_write_note`) | Core functionality — without this nothing works |
| Note versioning | `obsidian_note_versions` table with before/after/prompt | Safety net for file writes + future audit data |
| obsidian-headless | Docker container syncing vault on NAS | Without this, notes don't reach phone without PC |
| Cloudflare Tunnel | HTTPS exposure of MCP server | Without this, Claude can't reach NAS |
| Cloudflare MCP Portal | Zero Trust OAuth | Without this, MCP server is unprotected |
| Dedicated domain | ~3 EUR/year for Cloudflare DNS | Required by MCP Server Portal |
| Claude Custom Connector | Config in claude.ai | Entry point for the user |

**Explicitly out of MVP:**
- DynamoDB sync automation (current manual process continues)
- Obsidian semantic search
- Proactive article suggestions
- Monitoring/alerting
- Quality audit of note changes
- Defense-in-depth token in MCP server

### Post-MVP Features

**Phase 2 (Growth):**
- Automated DynamoDB → PostgreSQL sync (cron or event-driven)
- `obsidian_search` tool (grep/semantic search across notes)
- Proactive suggestions ("3 new articles about Poland")
- NAS/tunnel monitoring with Slack alerts
- Automated quality audit of note changes (using stored prompts + diffs)
- `obsidian_update_note` tool (partial edits instead of full file overwrite)

**Phase 3 (Expansion):**
- Full Lenie MCP tool suite (document processing, embedding generation, content download)
- Direct NAS backend ingestion (if tunnel proves reliable — could eliminate DynamoDB sync)
- Multi-vault Obsidian support
- Integration with other MCP clients

### Risk Mitigation Strategy

**Technical Risks:**
- *MCP protocol is new* — mitigated by using official Python SDK and existing community examples
- *Cloudflare MCP Portal is in Open Beta* — mitigated by having fallback to simple tunnel + authless if Portal doesn't work
- *obsidian-headless is new (Feb 2026)* — mitigated by community Docker image; fallback to Syncthing if headless proves unreliable
- *Claude overwrites Obsidian notes incorrectly* — mitigated by `obsidian_note_versions` table (full before/after history)

**Resource Risks:**
- Single developer, side project — mitigated by clear MVP boundary and educational value (learning is acceptable even if MVP takes longer)
- Obsidian Sync subscription expires 2026-11-02 — evaluate in September whether to renew or migrate to Syncthing

## Functional Requirements

### Article Discovery & Review

- FR1: User can retrieve a list of unreviewed articles (limit 6 by default, newest first), showing title, source, size in KB, user note, date, and total count of unreviewed articles. User can request more or apply filters (source, type, date range, size).
- FR2: User can retrieve the full markdown content and metadata of a specific article
- FR3: User can search articles by keyword or phrase across title, content, and user note. Results return title, source, snippet showing match context, and relevance ordering (most relevant first).
- FR4: User can delete an article from the database
- FR5: When writing an Obsidian note linked to an article, system automatically associates the note path with the article. User can mark the article as reviewed when work on it is complete.

### Obsidian Note Management

- FR6: User can read the full content of an Obsidian note within `02-wiedza/`
- FR7: User can create a new Obsidian note within `02-wiedza/`
- FR8: User can overwrite an existing Obsidian note within `02-wiedza/`
- FR9: User can delete an Obsidian note within `02-wiedza/`
- FR10: User can list notes in a folder or subfolder within `02-wiedza/`

### Note Version History

- FR11: System automatically saves the previous version of a note before every write operation
- FR12: System records the user prompt, content before, content after, and source article for each note change
- FR13: User can retrieve the version history of a specific note (date, user prompt, content before/after) to audit how the note evolved over time

### Claude Integration

- FR14: User can configure a Custom Connector in claude.ai pointing to the MCP server
- FR15: Claude on mobile can invoke all MCP tools (Lenie and Obsidian) through the Custom Connector

## Non-Functional Requirements

### Performance

- NFR1: MCP tool responses complete within 5 seconds for article list and note read operations, as measured by MCP server response logging in production
- NFR2: Article list (`lenie_unreviewed_articles`) with default limit of 6 returns within 2 seconds, as measured by MCP server response logging
- NFR3: Note write operations (including version save to DB) complete within 3 seconds, as measured by MCP server response logging including DB write timing
- *Note: These are initial estimates — to be validated and adjusted post-MVP*

### Security

- NFR4: All traffic between Claude and MCP server is encrypted via HTTPS (Cloudflare Tunnel), verified by tunnel configuration audit
- NFR5: MCP server cannot access filesystem outside `02-wiedza/` directory (path traversal prevention), verified by integration tests with traversal attempts
- NFR6: No credentials or secrets stored in MCP server Docker image — environment variables only, verified by image inspection in CI
- NFR7: Access to MCP server requires authentication via Cloudflare MCP Server Portal (Zero Trust OAuth) before reaching the server
- NFR8: MCP server is reachable from the public internet via Cloudflare Tunnel (no direct port exposure on NAS)

### Data Integrity

- NFR9: Every note write operation creates a version record in `obsidian_note_versions` before overwriting — no exceptions
- NFR10: Database transactions for article operations are atomic — partial writes are not allowed
- NFR11: Note version history is retained indefinitely (no automatic purging)

### Integration

- NFR12: MCP server implements MCP protocol compatible with Claude Custom Connector (streamable HTTP transport)
- NFR13: obsidian-headless container syncs vault changes to Obsidian Sync within 60 seconds of file write, as measured by file modification timestamp comparison between NAS and synced device
- NFR14: Vault changes written by MCP server propagate to phone and PC without requiring PC to be online (NAS-driven sync chain)
- NFR15: Obsidian vault on NAS is continuously synchronized with all user devices via Obsidian Sync (bidirectional, conflict resolution by Obsidian)
- NFR16: MCP server connects to existing PostgreSQL on `lenie-net` Docker network without additional configuration
