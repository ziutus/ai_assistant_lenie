---
workflow: check-implementation-readiness
date: 2026-04-15
project: lenie-server-2025
stepsCompleted:
  - step-01-document-discovery
  - step-02-prd-analysis
  - step-03-epic-coverage-validation
filesIncluded:
  prd: _bmad-output/planning-artifacts/prd.md
  architecture: _bmad-output/planning-artifacts/architecture.md
  epics: _bmad-output/planning-artifacts/epics/ (sharded)
  ux: not applicable (backend-focused, no UX docs yet)
---

# Implementation Readiness Assessment Report

**Date:** 2026-04-15
**Project:** lenie-server-2025

## Step 1 — Document Inventory

### Documents selected for assessment

| Type | Format | Path |
|---|---|---|
| PRD | whole | `_bmad-output/planning-artifacts/prd.md` |
| Architecture | whole | `_bmad-output/planning-artifacts/architecture.md` |
| Epics & Stories | sharded | `_bmad-output/planning-artifacts/epics/` (index.md + epic-20/26/27/28/29/33 + backlog.md) |
| UX Design | N/A | Not in scope — backend-focused phase, no UX spec yet |

### Resolved issues

- **Duplicate epics:** `epics.md` (whole) was archived to `archive/epics-whole-2026-04-15.md`. Sharded `epics/` is the canonical source.
- **Missing UX doc:** confirmed by user as intentional — UX is deferred, current focus is backend.

## Step 2 — PRD Analysis

### Functional Requirements

**Article Discovery & Review (FR1–FR5):**
- FR1: User can retrieve a list of unreviewed articles (limit 6 default, newest first), showing title/source/size KB/user note/date/total count. Supports filters (source, type, date range, size).
- FR2: User can retrieve the full markdown content and metadata of a specific article.
- FR3: User can search articles by keyword/phrase across title, content, user note. Returns title, source, snippet, relevance ordering.
- FR4: User can delete an article from the database.
- FR5: When writing an Obsidian note linked to an article, system automatically associates note path with article. User can mark article as reviewed when work is complete.

**Obsidian Note Management (FR6–FR10):**
- FR6: User can read the full content of an Obsidian note within `02-wiedza/`.
- FR7: User can create a new Obsidian note within `02-wiedza/`.
- FR8: User can overwrite an existing Obsidian note within `02-wiedza/`.
- FR9: User can delete an Obsidian note within `02-wiedza/`.
- FR10: User can list notes in a folder or subfolder within `02-wiedza/`.

**Note Version History (FR11–FR13):**
- FR11: System automatically saves the previous version of a note before every write operation.
- FR12: System records user prompt, content before, content after, and source article for each note change.
- FR13: User can retrieve the version history of a specific note (date, prompt, content before/after).

**Claude Integration (FR14–FR15):**
- FR14: User can configure a Custom Connector in claude.ai pointing to the MCP server.
- FR15: Claude on mobile can invoke all MCP tools (Lenie and Obsidian) through the Custom Connector.

**Total FRs: 15**

### Non-Functional Requirements

**Performance (NFR1–NFR3):**
- NFR1: MCP tool responses complete within 5s for article list and note read operations (measured via MCP server response logging).
- NFR2: `lenie_unreviewed_articles` with default limit 6 returns within 2s.
- NFR3: Note write operations (including version save to DB) complete within 3s.

**Security (NFR4–NFR8):**
- NFR4: All traffic between Claude and MCP server is encrypted via HTTPS (Cloudflare Tunnel).
- NFR5: MCP server cannot access filesystem outside `02-wiedza/` (path traversal prevention, verified by integration tests).
- NFR6: No credentials/secrets in MCP server Docker image — environment variables only (verified by image inspection in CI).
- NFR7: Access to MCP server requires authentication via Cloudflare MCP Server Portal (Zero Trust OAuth).
- NFR8: MCP server is reachable from public internet via Cloudflare Tunnel (no direct port exposure on NAS).

**Data Integrity (NFR9–NFR11):**
- NFR9: Every note write creates a version record in `obsidian_note_versions` before overwrite — no exceptions.
- NFR10: Database transactions for article operations are atomic — no partial writes.
- NFR11: Note version history retained indefinitely (no automatic purging).

**Integration (NFR12–NFR16):**
- NFR12: MCP server implements MCP protocol compatible with Claude Custom Connector (streamable HTTP transport).
- NFR13: obsidian-headless syncs vault changes to Obsidian Sync within 60s of file write.
- NFR14: Vault changes written by MCP server propagate to phone and PC without requiring PC online.
- NFR15: Obsidian vault on NAS continuously synchronized with all user devices via Obsidian Sync (bidirectional).
- NFR16: MCP server connects to existing PostgreSQL on `lenie-net` Docker network without additional configuration.

**Total NFRs: 16**

### Additional Requirements / Constraints

- **Project context:** Brownfield — extends existing NAS Docker stack (9 containers), Lenie backend, Obsidian integration.
- **Security stack:** Cloudflare Tunnel + Cloudflare MCP Server Portal (Zero Trust OAuth, single auth layer — Claude Custom Connector does not support additional auth headers).
- **Domain:** Dedicated low-cost domain (~3 EUR/year) via Cloudflare DNS; production `lenie-ai.eu` stays on AWS Route53.
- **Obsidian sync:** `obsidian-headless` container on NAS, reuses existing Obsidian Sync subscription (valid until 2026-11-02 — renew/migrate decision in September).
- **Write scope:** MCP restricted to `02-wiedza/` vault subdirectory only.
- **Versioning:** `obsidian_note_versions` table (id, note_path, content_before, content_after, user_prompt, article_id FK, changed_by, created_at).
- **Error contract:** 6 structured error codes (article_not_found, note_not_found, note_path_invalid, vault_write_failed, database_unavailable, version_save_failed).
- **Out of MVP:** DynamoDB sync automation, Obsidian semantic search, proactive suggestions, monitoring/alerting, quality audit of note changes, defense-in-depth token.
- **API versioning:** MVP exposes single unbumped version; MCP version string handshake starts in Phase 2.

### PRD Completeness Assessment

**Strengths:**
- FRs and NFRs are numbered, specific, and measurable (NFRs specify measurement methods).
- Clear MVP gate ("Claude on mobile successfully reads an article from Lenie, creates/updates an Obsidian note, change propagates via Obsidian Sync").
- Explicit out-of-MVP list prevents scope creep.
- User journeys map cleanly to required tools (Journey Requirements Summary table).
- Error handling contract defined with user-facing message patterns.
- Risk mitigation strategy covers technical and resource risks.
- API contract is canonical with stability guarantees (tool names, params, error codes).

**Potential gaps for downstream validation:**
- No explicit FR for `lenie_search` tool acceptance criteria (mentioned in Journey Requirements + tool table, but FR3 covers this — verify epic coverage).
- No explicit NFR for logging/observability beyond response logging for NFR1–NFR3 (monitoring deferred to Phase 2, acceptable for MVP).
- `obsidian-headless` (Feb 2026 release) — risk flagged, community image referenced; fallback plan to Syncthing exists.
- No NFR for backup/recovery of `obsidian_note_versions` table (NFR11 says retain indefinitely but doesn't address DB loss).
- MVP performance targets (NFR1–NFR3) explicitly flagged as "initial estimates — to be validated and adjusted post-MVP" — acceptable for MVP but epics should include measurement instrumentation.

## Step 3 — Epic Coverage Validation

### 🚨 CRITICAL FINDING — PRD/Epic Mismatch

The epics currently in `_bmad-output/planning-artifacts/epics/` **do not correspond to the current PRD** (`prd.md` — MCP Server MVP, FR1–FR15).

**Evidence:**
- Current PRD defines **15 FRs** (FR1–FR15) covering MCP tools, Obsidian notes in `02-wiedza/`, note version history, Claude Custom Connector.
- Existing epics (20, 26, 27, 28, 29, 33) reference FR numbers up to **FR43** — these map to earlier PRDs (Secrets Management, SQLAlchemy ORM Migration, Import Pipeline Maturity):
  - Epic 20: FR33–FR39 (Secrets Management — Vault/SSM migration)
  - Epic 26: FR1–FR13 (ORM Foundation — **FR numbers collide with MCP PRD but reference ORM requirements**)
  - Epic 27: FR14–FR30 (Document CRUD & API serving)
  - Epic 28: FR20–FR23, FR43 (Vector embeddings)
  - Epic 29: FR31–FR42 (Data pipeline migration)
  - Epic 33: Import Pipeline Maturity (cache consolidation, import_logs, article review tracking — ADR-014)
- **Zero matches** for PRD-specific terms in epic files: `MCP`, `Cloudflare`, `obsidian_note_versions`, `lenie_unreviewed`, `Remote MCP server`.
- Index `epics/index.md` lists Sprints 1–11 but **no sprint/epic for MCP Server MVP**.

### Coverage Matrix (Current PRD — MCP Server MVP)

| FR | PRD Requirement (MCP Server) | Epic Coverage | Status |
|----|------------------------------|---------------|--------|
| FR1 | `lenie_unreviewed_articles` — list unreviewed articles | **NOT FOUND** | ❌ MISSING |
| FR2 | `lenie_get_article` — full content + metadata | **NOT FOUND** | ❌ MISSING |
| FR3 | `lenie_search` — keyword/phrase search with snippets | **NOT FOUND** | ❌ MISSING |
| FR4 | `lenie_delete_article` — delete from DB | **NOT FOUND** | ❌ MISSING |
| FR5 | Auto-link note path to article + mark reviewed | Partially — Epic 33 Story 33.4 adds `obsidian_note_paths` + `reviewed_at` columns (prerequisite only) | ⚠ PARTIAL (schema only) |
| FR6 | `obsidian_read_note` in `02-wiedza/` | **NOT FOUND** | ❌ MISSING |
| FR7 | `obsidian_write_note` create new | **NOT FOUND** | ❌ MISSING |
| FR8 | `obsidian_write_note` overwrite existing | **NOT FOUND** | ❌ MISSING |
| FR9 | `obsidian_delete_note` | **NOT FOUND** | ❌ MISSING |
| FR10 | `obsidian_list_notes` | **NOT FOUND** | ❌ MISSING |
| FR11 | Auto-save previous version before every write | **NOT FOUND** | ❌ MISSING |
| FR12 | Record user_prompt + content_before/after + article_id | **NOT FOUND** | ❌ MISSING |
| FR13 | `obsidian_note_history` | **NOT FOUND** | ❌ MISSING |
| FR14 | Claude Custom Connector configuration | **NOT FOUND** | ❌ MISSING |
| FR15 | Claude mobile invokes all MCP tools | **NOT FOUND** | ❌ MISSING |

### NFR Coverage (Current PRD)

| NFR | Topic | Epic Coverage | Status |
|-----|-------|---------------|--------|
| NFR1–NFR3 | Performance (response times, write with versioning) | **NOT FOUND** | ❌ MISSING |
| NFR4 | HTTPS via Cloudflare Tunnel | **NOT FOUND** | ❌ MISSING |
| NFR5 | Filesystem sandboxing to `02-wiedza/` (path traversal prevention) | **NOT FOUND** | ❌ MISSING |
| NFR6 | No secrets in Docker image | **NOT FOUND** | ❌ MISSING |
| NFR7 | Cloudflare MCP Server Portal (Zero Trust OAuth) | **NOT FOUND** | ❌ MISSING |
| NFR8 | No direct port exposure (tunnel only) | **NOT FOUND** | ❌ MISSING |
| NFR9 | Versioning before every write — no exceptions | **NOT FOUND** | ❌ MISSING |
| NFR10 | Atomic DB transactions for article ops | Indirect — Epic 26 establishes ORM foundation | ⚠ INDIRECT |
| NFR11 | Indefinite retention of note versions | **NOT FOUND** | ❌ MISSING |
| NFR12 | MCP protocol compatibility (streamable HTTP) | **NOT FOUND** | ❌ MISSING |
| NFR13 | obsidian-headless sync within 60s | **NOT FOUND** | ❌ MISSING |
| NFR14 | Phone-PC propagation without PC online | **NOT FOUND** | ❌ MISSING |
| NFR15 | Continuous vault sync (bidirectional) | **NOT FOUND** | ❌ MISSING |
| NFR16 | MCP connects on `lenie-net` | **NOT FOUND** | ❌ MISSING |

### Coverage Statistics

- **Total PRD FRs:** 15
- **FRs fully covered in epics:** 0
- **FRs partially covered (prerequisite only):** 1 (FR5 — schema via Epic 33)
- **FRs missing:** 14
- **Coverage percentage (fully covered):** **0%**

- **Total PRD NFRs:** 16
- **NFRs covered:** 0 (1 indirect via ORM foundation)
- **Coverage percentage:** **0%**

### Missing Requirements — Recommended Epic Structure

The MCP Server MVP PRD requires creating a new sprint (e.g., **Sprint 12: MCP Server MVP**) with epics. Suggested breakdown:

**Critical Missing Epics:**

1. **Epic MCP-A: Lenie MCP Tools** — covers FR1, FR2, FR3, FR4, FR5 (read side of review logic) + NFR10, NFR16.
   - Stories for each tool; reuses existing `DocumentService`/`SearchService`.
   - Includes `mark_as_reviewed` parameter in `obsidian_write_note` (write-side of FR5).
2. **Epic MCP-B: Obsidian Vault Tools & Sandboxing** — covers FR6–FR10 + NFR5.
   - Path traversal prevention integration tests (NFR5 verification).
   - Restricted to `02-wiedza/`.
3. **Epic MCP-C: Note Version History** — covers FR11, FR12, FR13 + NFR9, NFR11.
   - Alembic migration for `obsidian_note_versions` table.
   - Pre-write versioning transaction + history reader tool.
4. **Epic MCP-D: MCP Server Container & Network** — covers NFR6, NFR12, NFR16.
   - Docker container in `compose.nas.yaml`, `lenie-net` integration, MCP SDK wiring.
5. **Epic MCP-E: Cloudflare Tunnel + Zero Trust Portal** — covers NFR4, NFR7, NFR8 + FR14.
   - Dedicated domain setup, Tunnel config, MCP Server Portal OAuth, Custom Connector config in claude.ai.
6. **Epic MCP-F: Obsidian Vault Sync (obsidian-headless)** — covers NFR13, NFR14, NFR15 + FR15 end-to-end validation.
   - Headless container + sync verification tests (60s NFR13 measurement).

**Impact:**
- Without these epics, **no PRD FR/NFR has an implementation path**.
- Existing sprints 6–11 are unrelated to this PRD and should not be treated as covering it.
- ⚠ Recommendation: before proceeding to Phase 4 implementation of the MCP Server MVP, **run `/bmad-agent-bmm-pm` → [CE] Create Epics and Stories** to produce a dedicated MCP Server epic set.

---

## Final Verdict — BLOCKED

**Status:** NOT READY for Phase 4 implementation.

**Reason:** 0% epic coverage of the MCP Server MVP PRD (`prd.md`). All current epics (sprints 6–11) address unrelated scopes.

**Workflow terminated early (after Step 3)** at user's decision. Steps 4 (UX alignment), 5 (quality review), 6 (final assessment) skipped — no epics to review qualitatively.

### Next action

Run `/bmad-agent-bmm-pm` → **[CE] Create Epics and Stories** to produce the Sprint 12: MCP Server MVP epic set following the structure proposed in Step 3. Re-run Implementation Readiness after epics exist.
