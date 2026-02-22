# Story 15.3: Remove Old api-gw-url-add Gateway and Clean Up

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **developer**,
I want to remove the standalone `api-gw-url-add` template, parameter file, deploy.ini entry, and CloudFormation stack,
so that no orphaned infrastructure remains after the consolidation.

## Acceptance Criteria

1. **Given** the `/url_add` endpoint works on the consolidated `api-gw-app` gateway (verified in Story 15.1 and 15.2), **When** the developer deletes the `lenie-dev-api-gw-url-add` CloudFormation stack from AWS, **Then** the stack is successfully deleted, **And** the old API Gateway and its resources are removed from AWS.

2. **Given** the CF stack is deleted, **When** the developer removes `api-gw-url-add.yaml` from `infra/aws/cloudformation/templates/`, **Then** the template file is deleted (not commented out or archived).

3. **Given** the template is removed, **When** the developer removes `api-gw-url-add.json` from `infra/aws/cloudformation/parameters/dev/`, **Then** the parameter file is deleted.

4. **Given** template and parameter files are removed, **When** the developer updates `infra/aws/cloudformation/deploy.ini`, **Then** the `templates/api-gw-url-add.yaml` commented-out entry is removed from the `[dev]` section, **And** the deployment order of remaining templates is correct (no dangling dependencies).

5. **Given** `infra/aws/cloudformation/smoke-test-url-add.sh` may reference the old gateway URL, **When** the developer reviews the smoke test, **Then** the script is confirmed to NOT reference `api-gw-url-add` (it uses `url-add` stack which is separate and still active).

6. **Given** documentation files reference the removed `api-gw-url-add.yaml` template, **When** the developer updates all affected documentation, **Then** all references to `api-gw-url-add.yaml` are removed or corrected to reflect the post-consolidation state (2 API Gateways: app + infra).

## Tasks / Subtasks

- [x] Task 1: Delete `lenie-dev-api-gw-url-add` CloudFormation stack from AWS (AC: #1)
  - [x] Verify `/url_add` works on `api-gw-app` gateway before deleting
  - [x] Run `aws cloudformation delete-stack --stack-name lenie-dev-api-gw-url-add --region us-east-1`
  - [x] Wait for deletion: `aws cloudformation wait stack-delete-complete --stack-name lenie-dev-api-gw-url-add --region us-east-1`
  - [x] Verify stack no longer exists: `aws cloudformation describe-stacks --stack-name lenie-dev-api-gw-url-add` should return error
- [x] Task 2: Remove `api-gw-url-add.yaml` template file (AC: #2)
  - [x] Delete `infra/aws/cloudformation/templates/api-gw-url-add.yaml`
  - [x] Verify file is removed (not commented out or archived)
- [x] Task 3: Remove `api-gw-url-add.json` parameter file (AC: #3)
  - [x] Delete `infra/aws/cloudformation/parameters/dev/api-gw-url-add.json`
- [x] Task 4: Update `deploy.ini` (AC: #4)
  - [x] Remove the commented-out line: `; templates/api-gw-url-add.yaml  ; UNUSED duplicate...`
  - [x] Verify no other template depends on `api-gw-url-add.yaml` (none do — it was already commented out)
  - [x] Verify remaining Layer 6 entries are correct: `api-gw-infra.yaml`, `api-gw-app.yaml`
- [x] Task 5: Review smoke test (AC: #5)
  - [x] Read `smoke-test-url-add.sh` — confirm it references stack `lenie-dev-url-add` (from `url-add.yaml`), NOT `lenie-dev-api-gw-url-add`
  - [x] No changes needed — the smoke test tests against `url-add.yaml` stack which is separate and still active
- [x] Task 6: Update documentation files (AC: #6)
  - [x] Update `infra/aws/cloudformation/CLAUDE.md` — remove `api-gw-url-add.yaml` row from API Gateway table, remove from Layer 6 deployment order, remove the note about `api-gw-url-add` lacking stage logging
  - [x] Update `infra/aws/CLAUDE.md` — update API Gateway service description (remove "+ 1 Chrome extension API" transitional reference), clean Key AWS Services table
  - [x] Update `infra/aws/README.md` — remove section "9. API Gateway - Chrome Extension (`api-gw-url-add.yaml`)", remove `api-gw-url-add.json` from parameter table, update section 15.6 to remove `api-gw-url-add.yaml` reference, renumber sections 10→9 through 15→14
  - [x] Update `docs/architecture-infra.md` — change API row from "3 API Gateways" to "2 API Gateways (infra, app)"
  - [x] Update `docs/observability.md` — remove `api-gw-url-add` references from the observability matrix and gap analysis

## Dev Notes

### Architecture Compliance

**CloudFormation Resource Removal Pattern (from Sprint 4 Architecture):**
- Delete resources cleanly — no commented-out remnants, no placeholder comments
- git history provides removal audit trail
- Verify no dangling dependencies before removing

**Post-Consolidation State (2 API Gateways):**
- `api-gw-app.yaml` — Main application API (11 endpoints including `/url_add` consolidated in Story 15-1)
- `api-gw-infra.yaml` — Infrastructure management API (7 endpoints)
- `api-gw-url-add.yaml` — **REMOVED** (this story)
- `url-add.yaml` — Lambda function with its own API Gateway (still active, separate from `api-gw-url-add.yaml`)

**Anti-patterns (NEVER do):**
- Archiving `api-gw-url-add.yaml` instead of deleting — git history preserves it
- Adding `# Removed: api-gw-url-add.yaml` comments to `deploy.ini`
- Modifying `api-gw-app.yaml` or `url-add.yaml` — this story is cleanup only
- Deleting the wrong stack (`lenie-dev-url-add` is NOT the target — only `lenie-dev-api-gw-url-add`)

### Critical Technical Context

**Stack to Delete:**
```
Stack name:    lenie-dev-api-gw-url-add
Template:      api-gw-url-add.yaml
API Gateway:   lenie_dev_add_from_chrome_extension (ID: 61w8tmmzkh)
Status:        UNUSED — was a duplicate of url-add.yaml's API Gateway
Resources:     REST API, API Key, Usage Plan, Usage Plan Key, Lambda Permission, Deployment
```

**Stack NOT to Delete (common confusion):**
```
Stack name:    lenie-dev-url-add
Template:      url-add.yaml
API Gateway:   lenie_dev_add_from_chrome_extension (ID: jg40fjwz61)
Status:        ACTIVE — Lambda function + its own API Gateway, still in deploy.ini
```

These are two DIFFERENT stacks created from two DIFFERENT templates. Only `lenie-dev-api-gw-url-add` is removed. The `lenie-dev-url-add` stack remains.

**deploy.ini Current State (Layer 6):**
```ini
; --- Layer 6: API ---
templates/api-gw-infra.yaml
templates/api-gw-app.yaml
; templates/api-gw-url-add.yaml  ; UNUSED duplicate — active Chrome ext API is in url-add.yaml. Delete stack lenie-dev-api-gw-url-add manually.
```

**deploy.ini Target State (Layer 6):**
```ini
; --- Layer 6: API ---
templates/api-gw-infra.yaml
templates/api-gw-app.yaml
```

**smoke-test-url-add.sh Analysis:**
The smoke test uses `STACK_NAME="${PROJECT_CODE}-${STAGE}-url-add"` which resolves to `lenie-dev-url-add` (from `url-add.yaml`), NOT `lenie-dev-api-gw-url-add`. The script dynamically retrieves the API endpoint and key from CloudFormation outputs — no hardcoded URLs. No changes needed for this story.

**Files to Delete:**
| File | Reason |
|------|--------|
| `infra/aws/cloudformation/templates/api-gw-url-add.yaml` | Template consolidated into api-gw-app.yaml (Story 15-1) |
| `infra/aws/cloudformation/parameters/dev/api-gw-url-add.json` | Parameter file for removed template |

**Files to Modify:**
| File | Action | Description |
|------|--------|-------------|
| `infra/aws/cloudformation/deploy.ini` | MOD | Remove commented-out `api-gw-url-add.yaml` line from Layer 6 |
| `infra/aws/cloudformation/CLAUDE.md` | MOD | Remove `api-gw-url-add.yaml` from API Gateway table and Layer 6 section |
| `infra/aws/CLAUDE.md` | MOD | Remove transitional Chrome ext API reference from API Gateway description |
| `infra/aws/README.md` | MOD | Remove section 9 (Chrome Extension API GW), remove from parameter table, update section 15.6 |
| `docs/architecture-infra.md` | MOD | Update API row: 3→2 API Gateways |
| `docs/observability.md` | MOD | Remove api-gw-url-add references from observability matrix and gaps |

**Files NOT to Touch:**
| File | Reason |
|------|--------|
| `infra/aws/cloudformation/templates/api-gw-app.yaml` | Already updated in Story 15-1 |
| `infra/aws/cloudformation/templates/url-add.yaml` | Separate stack, still active |
| `infra/aws/cloudformation/smoke-test-url-add.sh` | References `url-add` stack, not `api-gw-url-add` |
| `web_chrome_extension/*` | Already updated in Story 15-2 |
| `web_add_url_react/*` | Already updated in Story 15-2 |
| `docs/architecture-decisions.md` | Historical decisions — references are archival context |
| `_bmad-output/**` | Planning/implementation artifacts — not production documentation |

### Testing Requirements

1. **Pre-deletion verification:** Confirm `/url_add` works on consolidated `api-gw-app` gateway (Story 15-1 deployment must be done)
2. **Stack deletion:** `aws cloudformation describe-stacks --stack-name lenie-dev-api-gw-url-add` returns error after deletion
3. **File removal:** Verify `api-gw-url-add.yaml` and `api-gw-url-add.json` no longer exist in the repo
4. **deploy.ini:** Verify no commented-out `api-gw-url-add` line remains
5. **Documentation:** `grep -r "api-gw-url-add" docs/ infra/` returns zero matches in active documentation files (excluding `_bmad-output/` archives)
6. **No regression:** `smoke-test-url-add.sh -p lenie -s dev` still passes (tests `url-add` stack, unaffected)

### Previous Story Intelligence

**From Story 15-1 (Merge /url_add Endpoint — Status: done):**
- `/url_add` endpoint (POST + OPTIONS with CORS) successfully added to api-gw-app.yaml
- `UrlAddLambdaInvokePermission` resource added, scoped to `/*/*/url_add`
- Template size post-merge: 29,647 bytes (58% of 51,200 limit)
- api-gw-app.yaml now serves 11 endpoints
- Commit: `08a755b feat: merge /url_add endpoint into api-gw-app.yaml (Story 15-1)`
- deploy.ini already had `api-gw-url-add.yaml` commented out since earlier work
- **Key learning:** Code review caught stale documentation references — do a thorough doc sweep

**From Story 15-2 (Update Client Applications — Status: done):**
- Chrome extension URL updated: `jg40fjwz61` → `1bkc3kz7c9` (api-gw-app)
- React app URL was already correct (`1bkc3kz7c9` = api-gw-app)
- Both apps versioned and CHANGELOGs updated
- **Key learning:** Stale documentation references in CLAUDE.md, README.md, API_Usage.md were caught in code review — Story 15-3 should do the same for `api-gw-url-add` references
- Commit: `bcee6dd feat: update client apps to consolidated API Gateway (Story 15-2)`

**From Sprint 4 Git History (pattern):**
- Conventional commits: `feat:` for new features, `fix:` for corrections
- Story reference in commit message: `(Story 15-X)`
- Code review typically catches 2-7 documentation reference issues

### Project Structure Notes

- Story 15.3 is the third and final story in Epic 15 (API Gateway Consolidation)
- Depends on Story 15-1 (merge endpoint) and Story 15-2 (update clients) being deployed
- After this story, Epic 15 is complete — all 3 stories done
- Next: Epic 16 (Documentation Consolidation & Verification) or Epic 15 retrospective
- **Important:** The `lenie-dev-api-gw-url-add` CF stack deletion is an AWS operation that cannot be done by the dev agent alone — it requires AWS CLI access. If the dev agent cannot run AWS commands, this task should be flagged for manual execution.

### References

- [Source: _bmad-output/planning-artifacts/epics.md — Epic 15, Story 15.3]
- [Source: _bmad-output/planning-artifacts/architecture.md — Sprint 4, Post-Consolidation Cleanup (5-step sequence)]
- [Source: _bmad-output/planning-artifacts/architecture.md — Sprint 4, CloudFormation Resource Removal Pattern]
- [Source: _bmad-output/implementation-artifacts/15-1-merge-url-add-endpoint-into-api-gw-app-yaml.md — Previous story context]
- [Source: _bmad-output/implementation-artifacts/15-2-update-client-applications-and-version-releases.md — Previous story context]
- [Source: infra/aws/cloudformation/deploy.ini:44 — api-gw-url-add.yaml already commented out]
- [Source: infra/aws/cloudformation/templates/api-gw-url-add.yaml — Template to be deleted (177 lines)]
- [Source: infra/aws/cloudformation/parameters/dev/api-gw-url-add.json — Parameter file to be deleted]
- [Source: infra/aws/cloudformation/smoke-test-url-add.sh — References url-add stack, NOT api-gw-url-add]
- [Source: docs/architecture-decisions.md:177 — Historical: api-gw-url-add identified as UNUSED duplicate]
- [Source: infra/aws/cloudformation/CLAUDE.md — api-gw-url-add.yaml in API Gateway table and Layer 6 section]
- [Source: infra/aws/CLAUDE.md — API Gateway service description with transitional Chrome ext API reference]
- [Source: infra/aws/README.md:294 — Section 9 (Chrome Extension API GW) to be removed]
- [Source: docs/architecture-infra.md:36 — API row with "3 API Gateways"]
- [Source: docs/observability.md:63,173,179 — api-gw-url-add references in observability matrix]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

None

### Completion Notes List

- Deleted CloudFormation stack `lenie-dev-api-gw-url-add` from AWS (verified deletion complete)
- Verified `/url_add` endpoint exists on consolidated `api-gw-app` gateway before stack deletion
- Deleted template file `api-gw-url-add.yaml` and parameter file `api-gw-url-add.json`
- Cleaned `deploy.ini` — removed commented-out `api-gw-url-add.yaml` line from Layer 6
- Confirmed `smoke-test-url-add.sh` references `url-add` stack (not `api-gw-url-add`) — no changes needed
- Updated 5 documentation files to remove all `api-gw-url-add` references
- Renumbered `infra/aws/README.md` sections 10-15 → 9-14 after removing section 9
- Post-implementation grep confirmed zero matches for `api-gw-url-add` in `infra/` and `docs/` (except archival `docs/architecture-decisions.md`)
- `docs/architecture-decisions.md` intentionally NOT modified — historical/archival context
- **[Code Review]** Fixed API Gateway count: url-add.yaml still creates UrlAddApi, so there are 3 API Gateways (not 2). Corrected in CLAUDE.md, architecture-infra.md, README.md section 14.6.
- **[Code Review]** Fixed README Resource Summary: endpoint breakdown "infra 8" → "infra 7 + url-add 1", template count 34→33 (26 active + 2 commented + 5 account).
- **[Code Review]** Added missing /url_add endpoint to README section 7 api-gw-app endpoint table (was 10, now 11).
- **[Code Review]** Updated stale line number in observability.md (api-gw-app.yaml:589-598 → 640-649).

### Change Log

| Action | File | Details |
|--------|------|---------|
| DELETE | `infra/aws/cloudformation/templates/api-gw-url-add.yaml` | Removed template (177 lines) |
| DELETE | `infra/aws/cloudformation/parameters/dev/api-gw-url-add.json` | Removed parameter file |
| MODIFY | `infra/aws/cloudformation/deploy.ini` | Removed commented-out api-gw-url-add.yaml line from Layer 6 |
| MODIFY | `infra/aws/cloudformation/CLAUDE.md` | Removed api-gw-url-add.yaml from API Gateway table, Layer 6 section, logging note |
| MODIFY | `infra/aws/CLAUDE.md` | Updated API Gateway description (2→3 REST APIs after review fix), cloudformation subdirectory description |
| MODIFY | `infra/aws/README.md` | Removed section 9, renumbered 10-15→9-14, removed param table row, updated section 14.6; [Review] fixed template count 34→33, endpoint breakdown infra 8→7, added /url_add to endpoint table, fixed section 14.6 "Both"→"All three" |
| MODIFY | `docs/architecture-infra.md` | Changed API row: 3→"2 templates; 3 REST APIs" (review fix: url-add.yaml has own API Gateway) |
| MODIFY | `docs/observability.md` | Removed api-gw-url-add from observability matrix and gap analysis; [Review] fixed stale line ref 589→640 |
| AWS | `lenie-dev-api-gw-url-add` stack | Deleted CloudFormation stack from AWS |

### File List

- `infra/aws/cloudformation/templates/api-gw-url-add.yaml` — DELETED
- `infra/aws/cloudformation/parameters/dev/api-gw-url-add.json` — DELETED
- `infra/aws/cloudformation/deploy.ini` — MODIFIED
- `infra/aws/cloudformation/CLAUDE.md` — MODIFIED
- `infra/aws/CLAUDE.md` — MODIFIED
- `infra/aws/README.md` — MODIFIED
- `docs/architecture-infra.md` — MODIFIED
- `docs/observability.md` — MODIFIED
