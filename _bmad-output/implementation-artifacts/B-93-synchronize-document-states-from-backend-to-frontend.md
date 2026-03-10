# Story B-93: Synchronize Document States from Backend to Frontend

Status: done

## Story

As a **developer**,
I want the list of document states in the frontend to be fetched from the backend API instead of hardcoded,
so that adding a new state (like `TEMPORARY_ERROR`) doesn't require manual frontend updates and rebuilds.

## Acceptance Criteria

1. **Backend endpoint exists:** `GET /document_states` returns all values from `StalkerDocumentStatus`, `StalkerDocumentType`, and `StalkerDocumentStatusError` enums
2. **Frontend uses API:** `web_interface_react` list page populates state and type dropdowns from API response instead of hardcoded `<option>` elements
3. **Auto-sync:** Adding a new enum value in backend automatically appears in frontend without any frontend code change
4. **Existing behavior preserved:** Current filter behavior (selecting state/type, fetching filtered list) works identically
5. **Error resilience:** If `/document_states` fails, frontend falls back to last cached values (or reasonable defaults) and remains functional
6. **Auth required:** Endpoint requires `x-api-key` header (consistent with all other non-health endpoints)

## Tasks / Subtasks

- [x] Task 1: Backend — Add `GET /document_states` endpoint (AC: #1, #6)
  - [x] 1.1 Add route handler in `backend/server.py` returning all 3 enums as JSON
  - [x] 1.2 Add unit tests for the new endpoint (response format, enum completeness, auth)
- [x] Task 2: Frontend — Replace hardcoded dropdowns with API-driven values (AC: #2, #3, #4)
  - [x] 2.1 Create `useDocumentStates` hook to fetch and cache states from `/document_states`
  - [x] 2.2 Update `list.tsx` to use fetched states for `<select>` elements instead of hardcoded values
  - [x] 2.3 Add `localStorage` caching for fetched states to avoid extra request on every page load
- [x] Task 3: Error handling & fallback (AC: #5)
  - [x] 3.1 Implement fallback in `useDocumentStates` hook: use cached/default values if API fails
- [x] Task 4: Verification
  - [x] 4.1 Verify all 16 states appear in state dropdown (currently 13 hardcoded, missing `TRANSCRIPTION_DONE_AND_SPLIT_BY_CHAPTERS` and `DOCUMENT_INTO_DATABASE`)
  - [x] 4.2 Verify all 6 types appear in type dropdown (currently 4 hardcoded, missing `text_message` and `text`)
  - [x] 4.3 Verify filter behavior is unchanged after switch to dynamic dropdowns

## Dev Notes

### Backend Implementation

**Endpoint: `GET /document_states`**

This endpoint reads Python enum values in memory — no database query needed. Add to `backend/server.py` following the established pattern.

**Response format** (must follow existing API convention):
```json
{
    "status": "success",
    "message": "Document states retrieved",
    "encoding": "utf8",
    "states": ["ERROR", "URL_ADDED", "NEED_TRANSCRIPTION", ...],
    "types": ["movie", "youtube", "link", "webpage", "text_message", "text"],
    "errors": ["NONE", "ERROR_DOWNLOAD", ...]
}
```

**Enum imports already available in server.py context:**
- `StalkerDocumentStatus` — `backend/library/models/stalker_document_status.py` (16 values)
- `StalkerDocumentType` — `backend/library/models/stalker_document_type.py` (6 values)
- `StalkerDocumentStatusError` — `backend/library/models/stalker_document_status_error.py` (17 values)

**Auth:** Endpoint requires `x-api-key` — do NOT add to `exempt_paths` list. The frontend already sends this header with all requests.

**Route pattern** (from existing endpoints in server.py):
```python
@app.route('/document_states', methods=['GET', 'OPTIONS'])
def get_document_states():
    if request.method == 'OPTIONS':
        return {"status": "OK"}, 200
    # ... implementation
```

**No session/repository needed** — this is a pure enum read, no database interaction.

### Frontend Implementation

**File to modify:** `web_interface_react/src/modules/shared/pages/list.tsx`

**Current hardcoded states** (lines 63-78): 13 states as `<option>` elements. Missing: `TRANSCRIPTION_DONE_AND_SPLIT_BY_CHAPTERS`, `DOCUMENT_INTO_DATABASE`, `READY_FOR_TRANSLATION` (deprecated).

**Current hardcoded types** (lines 55-61): 4 types as `<option>` elements. Missing: `text_message`, `text`.

**Hook pattern** — create `useDocumentStates.ts` following the same pattern as existing hooks (`useList.ts`, `useManageLLM.ts`):
- Use `axios` for API call
- Access `apiUrl` and `apiKey` from `AuthorizationContext`
- Cache result in `localStorage` (key prefix: `lenie_document_states`)
- Return `{ states, types, errors, loading, error }` tuple
- On fetch failure: use `localStorage` cache, or empty arrays as last resort

**API client pattern** (from `useList.ts`):
```typescript
const response = await axios.get(`${apiUrl}/document_states`, {
    headers: { "x-api-key": `${apiKey}` }
});
```

**"ALL" option:** The frontend adds "ALL" as the first `<select>` option for "show all documents". This is a UI-only concept — do NOT include "ALL" in the backend response. The hook/component should prepend "ALL" to the fetched values.

### Lambda Consideration

This endpoint does NOT need to be added to AWS Lambda functions. The `/document_states` endpoint reads Python enums (no database, no internet). If needed in the future, it fits in **app-server-db** Lambda (no VPC requirement, but grouped with other metadata endpoints). For now, Flask server only.

### Project Structure Notes

- Backend endpoint: `backend/server.py` (add route handler)
- Backend tests: `backend/tests/unit/test_flask_endpoints_document_states.py` (new file)
- Frontend hook: `web_interface_react/src/modules/shared/hooks/useDocumentStates.ts` (new file)
- Frontend page: `web_interface_react/src/modules/shared/pages/list.tsx` (modify)
- No changes to `shared/` types needed — states/types remain plain strings
- No changes to `web_interface_app2/` — app2 does not have state filter dropdowns

### Architecture Compliance

- **Response format:** Must include `status`, `message`, `encoding` keys per existing API convention [Source: `backend/server.py` all endpoint handlers]
- **Auth pattern:** Uses `check_auth_header()` via `@app.before_request` — no changes needed [Source: `backend/server.py` lines 67-94]
- **Session teardown:** No session needed for this endpoint, but existing `@app.teardown_appcontext` handles cleanup [Source: `backend/server.py` lines 84-87]
- **Test pattern:** Use `pytest` fixture with `patch.object(server, "check_auth_header")` for auth bypass [Source: `backend/tests/integration/test_flask_endpoints_orm.py`]
- **Frontend hooks pattern:** Axios + AuthorizationContext + localStorage [Source: `web_interface_react/src/modules/shared/hooks/useList.ts`]
- **Ruff compliance:** `ruff check backend/` with line-length=120, zero warnings required

### Testing Requirements

**Backend unit tests** (`test_flask_endpoints_document_states.py`):
- `GET /document_states` returns HTTP 200 with correct format
- Response contains all 16 states from `StalkerDocumentStatus`
- Response contains all 6 types from `StalkerDocumentType`
- Response contains all 17 errors from `StalkerDocumentStatusError`
- `OPTIONS /document_states` returns HTTP 200 (CORS preflight)
- Missing `x-api-key` returns HTTP 400

**Frontend** — no formal test framework currently in place for React hooks. Manual verification that dropdowns populate correctly.

### Cross-Story Context (Epic 30)

This story (B-93) is **independent** of other Epic 30 stories. The dependency chain for the remaining stories is:
- B-94 (lookup tables) — independent of B-93
- B-95 (FK constraints) — depends on B-94
- B-96 (ORM model updates) — depends on B-95

When B-96 is completed, the `/document_states` endpoint could optionally be changed to read from lookup tables instead of Python enums. However, this is NOT required for B-93 — reading from Python enums is the correct approach now and will continue to work after B-94/B-95/B-96.

### References

- [B-93 definition: backlog.md](../../_bmad-output/planning-artifacts/epics/backlog.md#b-93-synchronize-document-states-from-backend-to-frontend)
- [ADR-010: Database Lookup Tables](../../docs/architecture-decisions.md#adr-010-database-lookup-tables-with-foreign-keys-for-enum-like-fields)
- [Backend enum: stalker_document_status.py](../../backend/library/models/stalker_document_status.py)
- [Backend enum: stalker_document_type.py](../../backend/library/models/stalker_document_type.py)
- [Backend enum: stalker_document_status_error.py](../../backend/library/models/stalker_document_status_error.py)
- [Frontend list page: list.tsx](../../web_interface_react/src/modules/shared/pages/list.tsx)
- [Frontend hooks: useList.ts](../../web_interface_react/src/modules/shared/hooks/useList.ts)
- [API auth: server.py](../../backend/server.py)

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

No issues encountered during implementation.

### Completion Notes List

- **Task 1 (Backend):** Added `GET /document_states` endpoint to `server.py`. Returns all enum values from `StalkerDocumentStatus` (16), `StalkerDocumentType` (6), and `StalkerDocumentStatusError` (17) as JSON. Follows established API response format (`status`, `message`, `encoding`). Supports CORS preflight via `OPTIONS`. Auth enforced via existing `@app.before_request` hook. 7 unit tests added covering response format, enum completeness, CORS, string types, and auth.
- **Task 2 (Frontend):** Created `useDocumentStates` hook (`useDocumentStates.ts`) using axios + `AuthorizationContext` pattern. Fetches states on mount, caches in `localStorage` under `lenie_document_states` key. Updated `list.tsx` to use dynamic dropdowns — replaced hardcoded `<option>` elements with `.map()` over fetched arrays. "ALL" option prepended as UI-only concept.
- **Task 3 (Fallback):** Hook catches fetch errors and falls back to `localStorage` cached values. If no cache exists, empty arrays used (dropdowns render only "ALL").
- **Task 4 (Verification):** Confirmed 16 states (was 13 hardcoded), 6 types (was 4 hardcoded), 17 errors returned. Frontend builds with zero TypeScript errors. No regressions in backend test suite (392 pass, 26 pre-existing failures in unrelated test files).

### Senior Developer Review (AI)

**Reviewer:** Claude Opus 4.6 | **Date:** 2026-03-10

**Issues Found:** 1 High, 3 Medium, 2 Low | **All H+M Fixed**

- **[H1] FIXED** — Endpoint count "19" not updated to "20" in 8+ documentation files (infrastructure-metrics.md SSOT, CLAUDE.md, backend/CLAUDE.md, README.md, project-overview.md, api-contracts-backend.md, source-tree-analysis.md, index.md). Updated all files and added `/document_states` to SSOT table.
- **[M1] FIXED** — `err: any` TypeScript anti-pattern in useDocumentStates.ts catch block → changed to `err: unknown` with proper type narrowing and `axios.isCancel()` check.
- **[M2] FIXED** — No AbortController cleanup in useEffect → added AbortController with cleanup return, prevents state updates on unmounted component.
- **[M3] FIXED** — `loading` initialized as `false` even without cache → changed to `useState(!cached)` so loading=true when no cached data exists.
- **[L1] NOT FIXED** — `errors` field fetched but unused in frontend. Acceptable — available for future error filter dropdown.
- **[L2] NOT FIXED** — Redundant localStorage re-read in catch block. Refactored to reuse `loadCached()` helper instead.

### Change Log

- 2026-03-10: Implemented B-93 — backend endpoint + frontend dynamic dropdowns + localStorage caching + error fallback
- 2026-03-10: Code review — 4 fixes (H1 docs endpoint count, M1 err:any→unknown, M2 AbortController cleanup, M3 loading init)

### File List

- `backend/server.py` (modified — added imports + `/document_states` route)
- `backend/tests/unit/test_flask_endpoints_document_states.py` (new — 7 unit tests)
- `web_interface_react/src/modules/shared/hooks/useDocumentStates.ts` (new — hook; review: AbortController, err:unknown, loading init)
- `web_interface_react/src/modules/shared/pages/list.tsx` (modified — dynamic dropdowns)
- `docs/infrastructure-metrics.md` (review fix — added `/document_states`, count 19→20)
- `docs/api-contracts-backend.md` (review fix — count 19→20)
- `docs/project-overview.md` (review fix — count 19→20)
- `docs/source-tree-analysis.md` (review fix — count 19→20)
- `docs/index.md` (review fix — count 19→20)
- `CLAUDE.md` (review fix — count 19→20)
- `backend/CLAUDE.md` (review fix — count 19→20, added `/document_states` to Metadata)
- `README.md` (review fix — count 19→20)
