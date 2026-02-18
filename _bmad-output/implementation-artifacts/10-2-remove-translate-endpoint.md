# Story 10.2: Remove `/translate` Endpoint

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **developer**,
I want to remove the `/translate` endpoint from Lambda, API Gateway, and frontend,
So that the broken endpoint no longer appears in the API surface.

## Acceptance Criteria

1. **AC1 — Lambda handler removed:** The `/translate` handler block in `infra/aws/serverless/lambdas/app-server-internet/lambda_function.py` (lines 56-83) is deleted. The `from library.translate import text_translate` import on line 7 is removed. The Lambda function no longer handles `/translate` requests. All remaining handlers (`/website_download_text_content`, `/ai_embedding_get`) continue to function.

2. **AC2 — API Gateway definition removed:** The `/translate` path definition (POST + OPTIONS) in `infra/aws/cloudformation/templates/api-gw-app.yaml` (lines 563-613) is deleted. The API Gateway template no longer includes the `/translate` path.

3. **AC3 — Frontend function removed:** `handleTranslate()` in `web_interface_react/src/modules/shared/hooks/useManageLLM.js` (lines 371-408) is deleted. The "Translate" button is removed from `InputsForAllExceptLink.jsx` (lines 41-47). All page components (webpage, youtube, movie) no longer destructure or pass `handleTranslate`. The React frontend loads and functions without errors.

4. **AC4 — Backend verified clean:** The backend has no `library.translate` module — `backend/library/translate.py` does not exist. Zero active references to `library.translate` exist in the production backend codebase (confirming the endpoint was already broken). The broken `from library.translate import text_translate` import in `backend/test_code/embeddings_search.py` is cleaned up. The `library.translate` reference in `backend/test_code/CLAUDE.md` is removed. The commented-out `translate_to_english()` method in `backend/library/stalker_web_document.py` (lines 243-280) is already fully disabled and returns `None` — no action needed.

5. **AC5 — Documentation updated:** All documentation files referencing `/translate` as an endpoint are updated: `docs/api-contracts-backend.md`, `docs/architecture-backend.md`, `infra/aws/serverless/CLAUDE.md`, `backend/CLAUDE.md`, `CLAUDE.md` (root), `README.md`. Endpoint counts are decremented to reflect removal (18 to 17 total in Flask; Lambda internet: 3 to 2 endpoints).

## Tasks / Subtasks

- [x] **Task 1: Remove `/translate` handler from Lambda function** (AC: #1)
  - [x] 1.1 Delete `from library.translate import text_translate` import (line 7) in `infra/aws/serverless/lambdas/app-server-internet/lambda_function.py`
  - [x] 1.2 Delete the `/translate` handler block (was actually `if`, not `elif` — first handler in chain; after removal, `/website_download_text_content` promoted from `elif` to `if`)
  - [x] 1.3 Verify remaining handlers (`/website_download_text_content`, `/ai_embedding_get`) are intact and unmodified
  - [x] 1.4 Verify no other code in the Lambda references `text_translate` or `library.translate`

- [x] **Task 2: Remove `/translate` from API Gateway CloudFormation template** (AC: #2)
  - [x] 2.1 Delete the `/translate` path block (POST + OPTIONS) in `infra/aws/cloudformation/templates/api-gw-app.yaml`
  - [x] 2.2 Validate template with cfn-lint after removal — passed with 0 errors, 0 warnings
  - [x] 2.3 Verify no other resources reference the removed `/translate` path within the template

- [x] **Task 3: Remove frontend `handleTranslate` and UI button** (AC: #3)
  - [x] 3.1 Delete `handleTranslate()` function from `web_interface_react/src/modules/shared/hooks/useManageLLM.js`
  - [x] 3.2 Remove `handleTranslate` from the hook's return object
  - [x] 3.3 Remove "Translate" button from `web_interface_react/src/modules/shared/components/SharedInputs/InputsForAllExceptLink.jsx`
  - [x] 3.4 Remove `handleTranslate` prop from `InputsForAllExceptLink` component parameter destructuring
  - [x] 3.5 Remove `handleTranslate` destructure from `webpage.jsx` and prop passing
  - [x] 3.6 Remove `handleTranslate` destructure from `youtube.jsx` and prop passing
  - [x] 3.7 Remove `handleTranslate` destructure from `movie.jsx` and prop passing

- [x] **Task 4: Verify and clean backend references** (AC: #4)
  - [x] 4.1 Confirm `backend/library/translate.py` does not exist
  - [x] 4.2 Remove broken `from library.translate import text_translate` import from `backend/test_code/embeddings_search.py` — also removed two `text_translate()` call sites (question translation + answer translation blocks)
  - [x] 4.3 Remove `library.translate` reference from `backend/test_code/CLAUDE.md`
  - [x] 4.4 Grep entire backend for `library.translate` — zero results in source code
  - [x] 4.5 Confirm `translate_to_english()` in `stalker_web_document.py` is already disabled (returns None, all code commented) — no action needed

- [x] **Task 5: Update documentation** (AC: #5)
  - [x] 5.1 Update `docs/api-contracts-backend.md` — removed `/translate` from Lambda internet endpoint list, updated count 19→18
  - [x] 5.2 Update `docs/architecture-web_interface_react.md` — removed "Translate (PL→EN)" from AI tool buttons
  - [x] 5.3 Update `docs/component-inventory-web_interface_react.md` — removed translate toggle, props, AI buttons, hook endpoints
  - [x] 5.4 Update `docs/integration-architecture.md` — removed "/translate exists only in AWS Lambda" line
  - [x] 5.5 Update `docs/project-overview.md` — removed "translate" from frontend AI tools description
  - [x] 5.6 Update `infra/aws/serverless/CLAUDE.md` — removed `/translate` from endpoint table, mapping table, known differences
  - [x] 5.7 Update `infra/aws/README.md` — removed `/translate` and `/ai_ask` (stale from 10-1) references
  - [x] 5.8 Update `web_interface_react/CLAUDE.md` — removed translate from page description, hook description, endpoint categories
  - [x] 5.9 Update root `CLAUDE.md` — removed `/translate` from frontend description, Lambda internet endpoints, Lambda-only line
  - [x] 5.10 Update `README.md` — checked, "translate" references were generic (unrelated to endpoint), no changes needed
  - [x] 5.11 Check `docs/CI_CD.md` — checked, references were generic usage, no changes needed

- [x] **Task 6: Codebase-wide verification** (AC: #1-5)
  - [x] 6.1 `grep -r "/translate"` across codebase — zero endpoint references in source code; also removed stale comment in `app-server-db/lambda_function.py`
  - [x] 6.2 `grep -r "handleTranslate"` across codebase — zero results in source code (only planning artifacts)
  - [x] 6.3 `grep -r "text_translate"` across codebase — zero results in source code (only disabled code in `stalker_web_document.py` comments and planning artifacts)
  - [x] 6.4 Semantic review: 19 paths in `api-gw-app.yaml` (10 app + 9 infra), documentation matches
  - [x] 6.5 Frontend build check: `npm run build` completed successfully (warnings all pre-existing, main.js reduced by 260B)

## Dev Notes

### Technical Requirements

**IMPORTANT CONTEXT — Endpoint is already broken:**
- The `/translate` endpoint references `from library.translate import text_translate` in the Lambda function, but the `library.translate` module does NOT exist in the backend codebase
- This means the Lambda function will crash with `ModuleNotFoundError` if any request hits `/translate`
- Removal is therefore zero-risk to active functionality — nothing is working to break
- The frontend "Translate" button exists and will call the endpoint, but it will always fail

**No Flask backend change needed:**
- Unlike story 10-1 (which removed `/ai_ask` from `server.py`), the `/translate` endpoint does NOT exist in `backend/server.py`
- The `/translate` endpoint exists ONLY in the AWS Lambda `app-server-internet` — it was a Lambda-only endpoint
- The epics file (FR6-FR9) correctly scopes this to Lambda, API Gateway, and frontend only

**Lambda handler structure (post story 10-1):**
- Story 10-1 refactored the Lambda's `if` chains to `if/elif/else` pattern
- The `/translate` handler is now an `elif` block (lines 56-83), not a standalone `if`
- After removing `/translate`, the remaining handlers are `/website_download_text_content` and `/ai_embedding_get`

**Frontend `handleTranslate` details:**
- Hardcoded to translate from Polish (`source_language: "pl"`) to English (`target_language: "en"`)
- Uses `Content-Type: application/x-www-form-urlencoded` (not JSON — different from other endpoints)
- Sets `text_english` field in Formik state with the translated text
- The button appears on all document editing pages except link: webpage, youtube, movie

**`stalker_web_document.py` — no action required:**
- Contains a `translate_to_english()` method (lines 243-280) that is completely disabled
- All logic is commented out; the method returns `None` immediately
- Contains commented references to `text_translate` from `library.translate`
- This dead code is not harmful and is outside the scope of this story (it was never active)

### Architecture Compliance

**Resource Deletion Checklist (from Epic 7/8 retro — MANDATORY):**
Before removing any resource, verify:
1. **Code references checked** — grep entire codebase for `/translate` as endpoint path
2. **Active state verified** — the `/translate` endpoint is defined in API Gateway but already broken (Lambda import fails)
3. **Dependency chain reviewed** — no downstream callers depend on `/translate` since the backend module never existed

**API Gateway template (`api-gw-app.yaml`) modification rules:**
- After story 10-1, the template already had `/ai_ask` removed
- Removing `/translate` further reduces the template size
- CORS OPTIONS mock integration for `/translate` must also be removed (not just the POST method)
- After removal, run cfn-lint validation

**Semantic review requirement (from Epic 8/9 retro):**
- After code changes, verify endpoint counts in all documentation match reality
- **[Review correction]**: Story 10-1 did NOT update the Flask endpoint count in `api-contracts-backend.md` (it remained at 19). Since `/translate` was never in server.py, the Flask count stays at 19. Only the Lambda internet endpoint count decreases (3→2).
- Lambda internet endpoint count changes from 3 (`/translate`, `/website_download_text_content`, `/ai_embedding_get`) to 2

**CloudFormation validation:**
- Run cfn-lint on modified `api-gw-app.yaml` before committing

### Library & Framework Requirements

**No new libraries or dependencies required.** This story is purely removal/deletion of existing code.

**Libraries/frameworks affected (existing — no version changes):**

| Component | Framework | Impact |
|-----------|-----------|--------|
| `lambda_function.py` | AWS Lambda (Python) | Remove one `elif event['path']` handler block + one import — no Lambda runtime changes |
| `api-gw-app.yaml` | CloudFormation (YAML) | Remove path from OpenAPI 3.0 inline Body — no template format changes |
| `useManageLLM.js` | React 18 + axios | Remove one async function + axios.post call — no dependency changes |
| `InputsForAllExceptLink.jsx` | React 18 | Remove one `<button>` element + one prop — no component API changes |

**Dependencies NOT to remove:**
- `axios` — still used by many other API calls in the frontend
- `library.ai` import in Lambda — still used by `/ai_embedding_get` handler
- `formik` — still used by all page components for form state management

### File Structure Requirements

**Files to MODIFY (code — 7 files):**

```
infra/aws/
├── serverless/lambdas/app-server-internet/
│   └── lambda_function.py                                 [MOD] Remove /translate handler (lines 56-83) + import (line 7)
├── cloudformation/templates/
│   └── api-gw-app.yaml                                   [MOD] Remove /translate path definition (lines 563-613)

web_interface_react/src/modules/shared/
├── hooks/
│   └── useManageLLM.js                                    [MOD] Remove handleTranslate function + export
├── components/SharedInputs/
│   └── InputsForAllExceptLink.jsx                         [MOD] Remove "Translate" button + prop
├── pages/
│   ├── webpage.jsx                                        [MOD] Remove handleTranslate destructure + prop
│   ├── youtube.jsx                                        [MOD] Remove handleTranslate destructure + prop
│   └── movie.jsx                                          [MOD] Remove handleTranslate destructure + prop
```

**Files to UPDATE (documentation — estimated 6-8 files):**

```
docs/
├── api-contracts-backend.md                               [MOD] Remove /translate from endpoint list, update counts
├── architecture-backend.md                                [MOD] Remove /translate references if present

infra/aws/serverless/
├── CLAUDE.md                                              [MOD] Remove /translate from Lambda endpoint mapping

backend/
├── CLAUDE.md                                              [MOD] Update endpoint count if referenced

CLAUDE.md (root)                                           [MOD] Update endpoint count, remove /translate references
README.md                                                  [MOD] Update endpoint count if referenced
```

**Files to NOT TOUCH:**

```
backend/server.py                                          [NO CHANGE] /translate never existed here
backend/library/stalker_web_document.py                    [NO CHANGE] translate_to_english() is already disabled
backend/library/ai.py                                      [NO CHANGE] Not related to /translate
```

**No files created or deleted.** All changes are modifications to existing files (code removal + documentation updates).

### Testing Requirements

**Automated tests:**
- Run `pytest backend/tests/` — all existing unit and integration tests must pass (no regressions)
- No new test files required (this is code removal, not feature addition)

**Manual verification checklist:**

1. **CloudFormation template validation:**
   - `cfn-lint infra/aws/cloudformation/templates/api-gw-app.yaml` — must pass with zero errors

2. **Frontend build verification:**
   - `cd web_interface_react && npm run build` — must complete without errors
   - Verify no warnings about missing imports or undefined references to `handleTranslate`

3. **Codebase-wide grep verification:**
   - `grep -r "/translate"` — review results: only planning artifacts and disabled code in `stalker_web_document.py` should remain
   - `grep -r "handleTranslate"` — must return ZERO results in source code
   - `grep -r "text_translate"` — only `stalker_web_document.py` (commented) should remain

4. **Semantic review:**
   - Count endpoints in `api-gw-app.yaml` paths section — verify documentation matches
   - Verify Lambda internet now has 2 endpoints (not 3): `/website_download_text_content`, `/ai_embedding_get`
   - Check all CLAUDE.md and README.md endpoint count statements

### Previous Story Intelligence (from Story 10-1)

**Key learnings from story 10-1 implementation:**
- Story 10-1 already refactored Lambda `if` chains to `if/elif/else` pattern — `/translate` is now an `elif` block
- Story 10-1 removed unused `import library.ai` and `llm_simple_jobs_model` from Lambda — verify what remains after `/translate` removal
- Story 10-1 found and fixed pre-existing bugs: `webpage.jsx` document_type typo, missing `handleRemoveNotNeededText` prop in youtube/movie
- Documentation updates required touching 13 files in 10-1 — anticipate similar scope for 10-2
- Code review in 10-1 found 6 issues (1 HIGH, 3 MEDIUM, 2 LOW) — expect similar vigilance needed
- Story 10-1 confirmed `api-contracts-backend.md` had a phantom endpoint (`/website_exist`) that was already cleaned up

**Commit message convention:** `chore: remove /translate endpoint from Lambda, API Gateway, and frontend`

### Git Intelligence

**Recent commits (from sprint-status and story 10-1):**

| Commit | Description | Relevance |
|--------|-------------|-----------|
| `6af45b9` | chore: remove /ai_ask endpoint from backend, Lambda, API Gateway, and frontend | **HIGH** — exact same pattern to follow |
| `eae71f0` | docs: complete Sprint 2 — cleanup, vision, documentation | MEDIUM — documentation update pattern |
| `b08d197` | chore: replace pytube with pytubefix | LOW |

**Key pattern from story 10-1 commit (6af45b9):**
- Single commit for all changes (code removal + documentation updates)
- Commit type: `chore` (cleanup/removal work)
- All doc updates included in same commit

### Project Structure Notes

- All modifications align with unified project structure — no new paths, modules, or naming introduced
- Frontend follows existing modular pattern: `modules/shared/hooks/`, `modules/shared/components/`, `modules/shared/pages/`
- CloudFormation template remains in existing location: `infra/aws/cloudformation/templates/api-gw-app.yaml`
- Lambda code in existing location: `infra/aws/serverless/lambdas/app-server-internet/`
- No conflicts or variances detected with existing conventions

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic 10, Story 10.2] — Story definition, acceptance criteria, BDD scenarios
- [Source: _bmad-output/planning-artifacts/prd.md#Endpoint Removal — /translate] — FR6-FR9 requirements
- [Source: _bmad-output/planning-artifacts/architecture.md#Implementation Patterns] — Resource Deletion Checklist, CF validation rules
- [Source: _bmad-output/planning-artifacts/architecture.md#Enforcement Guidelines] — AI Agent MUST rules for CF templates
- [Source: _bmad-output/implementation-artifacts/10-1-remove-ai-ask-endpoint.md] — Previous story patterns and learnings
- [Source: infra/aws/serverless/lambdas/app-server-internet/lambda_function.py:7,56-83] — Lambda handler + import
- [Source: infra/aws/cloudformation/templates/api-gw-app.yaml:563-613] — API GW path definition
- [Source: web_interface_react/src/modules/shared/hooks/useManageLLM.js:371-408,558] — Frontend hook function + export
- [Source: web_interface_react/src/modules/shared/components/SharedInputs/InputsForAllExceptLink.jsx:7,41-47] — UI button + prop
- [Source: web_interface_react/src/modules/shared/pages/webpage.jsx:56,76] — Page component reference
- [Source: web_interface_react/src/modules/shared/pages/youtube.jsx:55,75] — Page component reference
- [Source: web_interface_react/src/modules/shared/pages/movie.jsx:55,75] — Page component reference
- [Source: docs/api-contracts-backend.md:127-139] — API documentation entry
- [Source: backend/library/stalker_web_document.py:243-280] — Disabled translate_to_english() method (NO ACTION)

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (claude-opus-4-6)

### Debug Log References

### Completion Notes List

- Ultimate context engine analysis completed — comprehensive developer guide created
- Story created on 2026-02-16 by BMad create-story workflow
- 12+ source files analyzed across Lambda, CloudFormation, frontend, backend, and documentation
- 5 acceptance criteria defined with specific file locations and line numbers
- 6 tasks with 24 subtasks mapped to acceptance criteria
- Key safety insight: endpoint is already broken (library.translate module missing) — removal is zero-risk
- Previous story (10-1) intelligence integrated: Lambda refactored to elif pattern, documentation update scope established
- Implementation completed on 2026-02-16 by Claude Opus 4.6
- Discovery: `/translate` handler was `if` (first in chain), not `elif` as story described — after removal, `/website_download_text_content` promoted from `elif` to `if`
- Extra cleanup: removed stale `/translate` comment in `app-server-db/lambda_function.py` (not in original task list)
- Extra cleanup: removed stale `/ai_ask` references in `infra/aws/README.md` (leftover from story 10-1)
- Extra cleanup: removed `text_translate()` call sites in `embeddings_search.py` (beyond just the import)
- Backend tests: 16 passed, 6 failed (all pre-existing failures in markdown/transcript tests — not regressions)
- Ruff lint: 67 errors all pre-existing
- Frontend build: passed, main.js reduced by 260 bytes

### File List

**Code files modified (8):**
- `infra/aws/serverless/lambdas/app-server-internet/lambda_function.py` — Removed `/translate` handler + import
- `infra/aws/cloudformation/templates/api-gw-app.yaml` — Removed `/translate` path (POST + OPTIONS)
- `web_interface_react/src/modules/shared/hooks/useManageLLM.js` — Removed `handleTranslate` function + export
- `web_interface_react/src/modules/shared/components/SharedInputs/InputsForAllExceptLink.jsx` — Removed Translate button + prop
- `web_interface_react/src/modules/shared/pages/webpage.jsx` — Removed `handleTranslate` destructure + prop
- `web_interface_react/src/modules/shared/pages/youtube.jsx` — Removed `handleTranslate` destructure + prop
- `web_interface_react/src/modules/shared/pages/movie.jsx` — Removed `handleTranslate` destructure + prop
- `backend/test_code/embeddings_search.py` — Removed `text_translate` import + 2 call sites

**Additional code files cleaned (2):**
- `infra/aws/serverless/lambdas/app-server-db/lambda_function.py` — Removed stale `/translate` comment
- `backend/test_code/CLAUDE.md` — Removed `library.translate` from module list

**Documentation files updated (10):**
- `docs/api-contracts-backend.md` — Removed `/translate` from Lambda internet list (Flask count restored to 19 — `/translate` was never in server.py)
- `docs/architecture-web_interface_react.md` — Removed "Translate (PL→EN)" from AI tool buttons
- `docs/component-inventory-web_interface_react.md` — Removed translate props, AI buttons, hook endpoints (restored "translate toggle" in search.jsx — unrelated to `/translate` endpoint)
- `docs/integration-architecture.md` — Removed "/translate exists only in AWS Lambda" line
- `docs/project-overview.md` — Removed "translate" from frontend AI tools
- `infra/aws/serverless/CLAUDE.md` — Removed `/translate` from 3 sections (endpoint table, mapping, known differences)
- `infra/aws/README.md` — Removed `/translate` and stale `/ai_ask` references
- `web_interface_react/CLAUDE.md` — Removed translate from 3 sections + fixed "translation" in description line and InputsForAllExceptLink description
- `CLAUDE.md` (root) — Removed `/translate` from 3 sections
- `_bmad-output/implementation-artifacts/10-2-remove-translate-endpoint.md` — This file (status + checkboxes)

**Files checked, no changes needed (4):**
- `backend/server.py` — `/translate` never existed here
- `backend/library/stalker_web_document.py` — `translate_to_english()` already disabled
- `README.md` — "translate" references are generic, not endpoint-specific
- `docs/CI_CD.md` — "translate" references are generic, not endpoint-specific

### Change Log

| Date | Change | Author |
|------|--------|--------|
| 2026-02-16 | Story created by BMad create-story workflow | Claude Opus 4.6 |
| 2026-02-16 | Implementation completed — all 6 tasks, 24 subtasks done. 20 files modified. | Claude Opus 4.6 |
| 2026-02-16 | Code review: 6 findings (1 HIGH, 3 MEDIUM, 2 LOW). All 6 fixed: Flask endpoint count restored to 19, search.jsx translate toggle restored in docs, CLAUDE.md "translation" references cleaned, `langauge` typo fixed in embeddings_search.py, Dev Notes corrected. | Claude Opus 4.6 |
