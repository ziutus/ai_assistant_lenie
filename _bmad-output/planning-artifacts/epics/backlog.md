## Sprint 6: Security Verification

### B-64: Verify Pre-Commit Secret Detection

As a **developer**,
I want to verify that pre-commit hooks correctly block commits containing secrets,
so that I have confidence the defense-in-depth secret detection actually works end-to-end.

**Origin:** Epic 19 retrospective — a real API key was committed (478b62c) because pre-commit hooks were misconfigured at the time. Since fixed, but never verified.

**Current setup (`.pre-commit-config.yaml`):**
- **Gitleaks v8.30.0** — regex-based offline detection (fast)
- **TruffleHog v3.93.4** — online verification of detected secrets

**Acceptance Criteria:**

**Given** pre-commit hooks are installed (`pre-commit install`)
**When** the developer attempts to commit a file containing a fake AWS access key (e.g., `AKIAIOSFODNN7EXAMPLE`)
**Then** at least one of the two tools (Gitleaks or TruffleHog) blocks the commit
**And** the error message clearly identifies the detected secret

**Given** the developer attempts to commit a fake OpenAI API key (e.g., `sk-proj-fake1234567890abcdefg`)
**When** the pre-commit hooks run
**Then** at least one tool blocks the commit

**Given** the developer attempts to commit a fake generic password in a config file (e.g., `PASSWORD=SuperSecret123!`)
**When** the pre-commit hooks run
**Then** at least one tool blocks the commit

**Given** all secret types are tested
**When** the developer documents the results
**Then** a test report is created documenting: which tools caught which secret types, any false negatives, and recommendations for `.gitleaks.toml` tuning if needed

**Given** a file contains no secrets (normal code)
**When** the developer commits it
**Then** both tools pass without blocking

**Technical notes:**
- Create temporary test files with fake secrets — do NOT use real credentials
- Remove test files after verification (do not commit them)
- Document results in `docs/security/pre-commit-verification.md`
- If either tool has blind spots, consider adding custom rules to `.gitleaks.toml`
- Test both `pre-commit` and `pre-push` stages

**Status:** backlog

---

## Backlog: Frontend Architecture & API Contract

### Overview

Work completed and planned to address frontend-backend type drift and shared code infrastructure. The `shared/` TypeScript package was extracted (B-49) and a strategy document for full API type synchronization was written (`docs/api-type-sync-strategy.md`). The main backlog item (B-50) covers the multi-phase implementation of Pydantic → OpenAPI → generated TypeScript types.

### Completed Work (Non-Sprint)

**B-49: Extract Shared TypeScript Types to shared/ Package** — DONE (2026-02-25)
- Created `shared/` package with domain types: `WebDocument`, `ApiType`, `SearchResult`, `ListItem`
- Added constants (`DEFAULT_API_URLS`) and factory values (`emptyDocument`)
- Both frontends (`web_interface_react/`, `web_interface_app2/`) reference via `@lenie/shared` alias (tsconfig paths + Vite resolve.alias)
- No build step — Vite transpiles directly via esbuild
- Commit: 64e3213

**B-51: Frontend Deployment Scripts with SSM** — DONE (2026-02-25)
- Created `deploy.sh` for `web_interface_react/` and `web_interface_app2/`
- Scripts resolve S3 bucket name and CloudFront distribution ID from SSM Parameter Store
- Support `--skip-build` and `--skip-invalidation` flags
- Commit: f2432ce

### B-50: API Type Synchronization Pipeline (Pydantic → OpenAPI → TypeScript)

**Problem:** Frontend (`shared/types/`) and backend (`backend/library/`) define the same data structures independently, leading to drift. Known issues documented in `docs/api-type-sync-strategy.md`:

| Issue | Detail |
|-------|--------|
| `id` type mismatch | TS: `string`, Python: `int` (serial PK) |
| `WebDocument` missing fields | Backend returns 13 fields not in TS interface |
| `ListItem` field count | TS: 5 fields, backend: 10 |
| `SearchResult` field count | TS: 5 fields, backend: 12 |
| Enums as plain strings | Backend has typed enums, frontend treats as `string` |
| No contract | No OpenAPI, JSON Schema, or Pydantic — backend uses custom classes + raw dicts |

**Chosen approach:** Python Pydantic models (source of truth) → OpenAPI schema (generated) → TypeScript types (generated)

**Implementation phases (from `docs/api-type-sync-strategy.md`):**

1. **Phase 1: Pydantic Response Models** — Create Pydantic v2 models in `backend/library/models/schemas/` for all API response shapes (WebDocumentResponse, WebDocumentListItem, SearchResultItem, ListResponse, SearchResponse, ErrorResponse)
2. **Phase 2: Use Models in Flask Routes** — Replace raw dict returns with Pydantic model serialization in `server.py` and Lambda handlers
3. **Phase 3: Generate OpenAPI Schema** — Manual export script or flask-smorest integration to produce `docs/openapi.json`
4. **Phase 4: Generate TypeScript from OpenAPI** — Use `openapi-typescript` to generate `shared/types/generated.ts` from OpenAPI schema
5. **Phase 5: CI Integration** — Add generation + diff check to CI pipeline to prevent future drift

**Migration path:** Incremental, one endpoint at a time. Start with `/website_get`, then `/website_list`, `/website_similar`. Hand-written `shared/types/` coexists with generated types during migration.

**Status:** backlog
**Strategy document:** `docs/api-type-sync-strategy.md`
**Depends on:** B-49 (shared types package) — DONE
