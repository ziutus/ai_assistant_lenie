# Story 16.2: Create Automated Documentation Drift Verification Script

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **developer**,
I want an automated script that detects documentation metric drift by comparing documented counts against actual infrastructure,
So that future discrepancies are caught early instead of accumulating silently.

## Acceptance Criteria

1. **Given** `docs/infrastructure-metrics.md` exists as the single source of truth, **When** the developer creates `scripts/verify-documentation-metrics.sh`, **Then** the script compares documented counts against actual counts by:
   - Counting endpoints in `api-gw-app.yaml` and `api-gw-infra.yaml` OpenAPI paths
   - Counting templates listed in `deploy.ini`
   - Counting total `.yaml` template files in `infra/aws/cloudformation/templates/`
   - Counting Lambda function definitions across templates
   - Counting endpoints in `backend/server.py`

2. **Given** the verification script exists, **When** the developer runs it, **Then** it reports any discrepancies between documented and actual counts **And** exits with code 0 if all counts match, non-zero if discrepancies found

3. **Given** the script runs successfully after Story 16.1 updates, **When** the developer verifies the output, **Then** zero discrepancies are reported

4. **Given** the `scripts/` directory may not exist, **When** the developer creates the script, **Then** the directory is created if needed **And** the script is executable (`chmod +x`)

## Tasks / Subtasks

- [x] Task 1: Create `scripts/` directory and script file (AC: #4)
  - [x] 1.1: Create `scripts/` directory if it doesn't exist
  - [x] 1.2: Create `scripts/verify-documentation-metrics.sh` with bash shebang and `set -e`
  - [x] 1.3: Make script executable (`chmod +x`)
- [x] Task 2: Implement documented count extraction from `docs/infrastructure-metrics.md` (AC: #1)
  - [x] 2.1: Parse Flask endpoint count (line: `**Total endpoints: 19**` or table row count)
  - [x] 2.2: Parse api-gw-app endpoint path count (line: `**api-gw-app ... — 11 endpoint paths:**`)
  - [x] 2.3: Parse api-gw-infra endpoint path count (line: `**api-gw-infra ... — 7 endpoint paths:**`)
  - [x] 2.4: Parse url-add endpoint count (line: `**url-add ... — 1 endpoint path:**`)
  - [x] 2.5: Parse Lambda function total (line: `**Total: 12 Lambda functions in AWS**`)
  - [x] 2.6: Parse CF-managed Lambda count (line: `**CF-managed via deploy.ini (10 functions):**`)
  - [x] 2.7: Parse deploy.ini template count (line: `**Templates in deploy.ini [dev]: 26**`)
  - [x] 2.8: Parse total template file count (line: `**Total .yaml files in templates/: 33**`)
- [x] Task 3: Implement actual infrastructure count verification (AC: #1)
  - [x] 3.1: Count Flask routes via `grep -cE '@app\.route' backend/server.py`
  - [x] 3.2: Count api-gw-app.yaml unique paths from OpenAPI Body
  - [x] 3.3: Count api-gw-infra.yaml unique paths from OpenAPI Body
  - [x] 3.4: Count url-add.yaml endpoint (PathPart resource)
  - [x] 3.5: Count Lambda functions: CF-managed (AWS::Lambda::Function in templates listed in deploy.ini) + non-CF (hardcoded names in api-gw-app.yaml)
  - [x] 3.6: Count active templates in deploy.ini [dev] section (non-commented `templates/` lines)
  - [x] 3.7: Count total `.yaml` files in `infra/aws/cloudformation/templates/`
- [x] Task 4: Implement comparison and reporting (AC: #2)
  - [x] 4.1: Compare each documented count vs actual count
  - [x] 4.2: Display pass/fail per metric with expected vs actual values
  - [x] 4.3: Exit code 0 on all pass, non-zero on any failure
  - [x] 4.4: Summary line with total checks passed/failed
- [x] Task 5: Run verification and confirm zero drift (AC: #3)
  - [x] 5.1: Execute script from project root
  - [x] 5.2: Verify all checks pass (exit code 0)
  - [x] 5.3: Intentionally modify a count to verify failure detection works

## Dev Notes

### Technical Requirements

- **Language:** Bash (POSIX-compatible where practical, but GNU grep/sed allowed — project runs on Linux/MSYS2)
- **Script location:** `scripts/verify-documentation-metrics.sh` — new directory, new file
- **Execution context:** Script MUST be run from the project root directory (`lenie-server-2025/`). All paths should be relative to project root.
- **Exit codes:** `0` = all checks pass, `1` = one or more discrepancies found
- **No external dependencies:** Use only standard bash tools: `grep`, `wc`, `find`, `sed`, `awk`. No Python, no jq, no external packages.
- **No colors in output:** Match existing project bash script style (see `infra/aws/serverless/zip_to_s3.sh` — plain text, no ANSI codes)
- **Error handling:** `set -e` at top. If a source file is missing (e.g., `server.py`, `deploy.ini`), report error and exit non-zero rather than silently skipping.

### Architecture Compliance

- **Architecture pattern (from architecture.md):** Documentation Metrics File Pattern (B-19) — metrics organized by deployment perspective (Flask Server / AWS Serverless / CloudFormation). The verification script must check counts matching this same 3-perspective structure.
- **Architecture anti-pattern to avoid:** "Creating complex scripts when a simple grep/count suffices" — keep the script straightforward, one check per metric, no over-engineering.
- **Sprint 1 Gen 2+ conventions:** Not directly applicable (no CF templates created), but script should follow bash conventions consistent with existing project scripts.
- **NFR14:** "An automated verification script exists that detects documentation metric drift and can be run as part of CI or manual review" — script must be CI-friendly (deterministic exit codes, no interactive prompts, no TTY requirement).
- **NFR13:** Single source of truth is `docs/infrastructure-metrics.md` — script reads documented values FROM this file, not from scattered documentation files.

### Library / Framework Requirements

No external libraries or frameworks. Pure bash with standard GNU coreutils:

| Tool | Purpose | Notes |
|------|---------|-------|
| `grep` | Pattern matching for counting routes, paths, templates | Use `-c` for count, `-E` for extended regex |
| `wc -l` | Line counting | Pipe from grep/find when `-c` not suitable |
| `sed` | Text extraction from metrics file | Extract numbers from formatted markdown lines |
| `find` | Count .yaml files in templates directory | `-name "*.yaml" -type f` |
| `awk` | Optional: extract numbers from complex patterns | Use only if sed is insufficient |

**DO NOT** introduce: Python, jq, yq, node, or any other runtime. The script must run on a bare Linux/MSYS2 system with only coreutils installed.

### File Structure Requirements

**Files created by this story:**
```
scripts/                                    [NEW] Directory
  verify-documentation-metrics.sh           [NEW] Main verification script (chmod +x)
```

**Files READ by the script (not modified):**
```
docs/infrastructure-metrics.md              — Source of documented counts (single source of truth)
backend/server.py                           — Actual Flask route count (@app.route)
infra/aws/cloudformation/deploy.ini         — Actual template count ([dev] section)
infra/aws/cloudformation/templates/         — Actual .yaml file count
infra/aws/cloudformation/templates/api-gw-app.yaml    — Actual app API paths (OpenAPI Body)
infra/aws/cloudformation/templates/api-gw-infra.yaml   — Actual infra API paths (OpenAPI Body)
infra/aws/cloudformation/templates/url-add.yaml        — Actual url-add endpoint (1 path)
```

**No files are modified by this story** — it is purely additive (1 new directory + 1 new script).

**Parsing patterns for each source file:**

| Source File | What to Count | Grep Pattern |
|------------|---------------|--------------|
| `backend/server.py` | Flask routes | `@app\.route` |
| `deploy.ini` | Active templates in [dev] | `^\s*templates/` (non-commented lines) |
| `templates/` directory | Total .yaml files | `find ... -name "*.yaml" -type f` |
| `api-gw-app.yaml` | Unique API paths | `^\s+/[a-zA-Z_]+:\s*$` (top-level path entries in OpenAPI) |
| `api-gw-infra.yaml` | Unique API paths | `^\s+/infra/[a-zA-Z_/]+:\s*$` (path entries in OpenAPI) |
| `url-add.yaml` | Endpoint count | Fixed: 1 (PathPart resource defines single `/url_add`) |

**CRITICAL — api-gw-app.yaml path counting:**
The OpenAPI Body has paths at indentation level 8 spaces (inside `Body` > `paths`). Each path like `/website_list:` appears at this level. Methods (`get:`, `post:`, `options:`) appear deeper. Count only top-level path entries, NOT methods. The regex must match lines like:
```
        /website_list:
        /url_add:
```
But NOT match method lines like:
```
          get:
          options:
```

**CRITICAL — api-gw-infra.yaml path counting:**
Same pattern but paths are multi-segment: `/infra/sqs/size:`, `/infra/database/start:`. These appear at indentation ~12 spaces (deeper nesting in the OpenAPI body). Count unique path entries ending with `:`.

### Testing Requirements

**No unit tests required** — this is a standalone bash script, not a Python module.

**Manual verification procedure:**

1. **Happy path:** Run `bash scripts/verify-documentation-metrics.sh` from project root. All checks must pass, exit code 0.
2. **Failure detection:** Temporarily change a count in `docs/infrastructure-metrics.md` (e.g., change "19" to "20" for Flask endpoints), run script, verify it reports the discrepancy and exits non-zero. Revert the change afterward.
3. **Missing file handling:** Temporarily rename `backend/server.py`, run script, verify it reports a clear error about the missing file and exits non-zero. Revert.
4. **Cross-platform:** Script must work on both Linux (CI) and MSYS2/Git Bash (developer's Windows environment). Avoid bashisms that break on MSYS2 — specifically:
   - Use `find` with explicit `-type f` (MSYS2 find vs Windows find.exe conflict — use full relative path `find infra/aws/...`)
   - Avoid `readarray` / `mapfile` (not available in older bash versions on MSYS2)
   - Use `grep -c` instead of `grep | wc -l` where possible (simpler, avoids pipe issues)

**Existing test suite impact:** None — no Python code modified, no existing tests affected. The 6 pre-existing unit test failures (markdown/transcript tests noted in Story 16.1) are unrelated.

### Previous Story Intelligence (Story 16.1)

**Key learnings from Story 16.1 that DIRECTLY impact this story:**

1. **Verified actual counts (as of 2026-02-21)** — use these as expected values:
   - Flask server.py: **19 routes** (including root `/` and `/version`)
   - api-gw-app.yaml: **11 unique paths**
   - api-gw-infra.yaml: **7 unique paths**
   - url-add.yaml: **1 path**
   - Lambda functions total: **12** (10 CF-managed + 2 non-CF)
   - deploy.ini [dev]: **26 templates**
   - Total .yaml files in templates/: **33**

2. **Root `/` endpoint was the source of the original discrepancy** — prior docs said "18 endpoints" because they excluded the root `/` route. The script must count ALL `@app.route` decorators including `/`.

3. **Non-CF Lambda functions matter** — `lenie_2_db` and `lenie_2_internet` are referenced in `api-gw-app.yaml` but not managed by CloudFormation. Story 16.1 counted them in the total (12 = 10 CF + 2 non-CF). The script should verify this total.

4. **Code review findings fixed in 16.1:**
   - `/url_add` exists in BOTH Flask (direct DB) AND AWS (SQS flow) — it is NOT Flask-only
   - `docs/architecture-backend.md` had a ghost endpoint `website_exist` that was removed
   - Story 16.1 fixed 10 files (not just the 7 originally scoped)

5. **Grep verification approach from 16.1:** Used `grep "18 endpoints"` across docs to verify no stale references remain. The verification script should take a similar approach — use grep patterns that reliably extract counts from actual source files.

6. **`lambda-rds-start.yaml` is NOT in deploy.ini** — it exists as a file in templates/ but is commented out / superseded by `api-gw-infra.yaml`. This is why deploy.ini count (26) differs from total files count (33). The script must count these separately.

### Git Intelligence

Recent commits (Sprint 4, most relevant):
- `e72235d` feat: complete Epic 15 — API Gateway consolidation, retro, and PRD fix (Story 15-3)
- `bcee6dd` feat: update client apps to consolidated API Gateway (Story 15-2)
- `08a755b` feat: merge /url_add endpoint into api-gw-app.yaml (Story 15-1)
- `00069d5` fix: remove stale Elastic IP references from docs and template description (Story 14-1 review)
- `edc94c6` fix: consolidate rds-start Lambda and remove git-webhooks endpoint (Story 14-2)

**Actionable insights:**
- Epic 15 consolidated API Gateway — the current api-gw-app.yaml has 11 paths (including /url_add added in `08a755b`). The script must count the post-consolidation state.
- Story 14-2 (`edc94c6`) consolidated rds-start Lambda into api-gw-infra.yaml — `lambda-rds-start.yaml` is now redundant (exists in templates/ but NOT in deploy.ini). The script's template count logic must handle this distinction.
- All infrastructure changes from Sprints 1-4 (Epics 1-15) and Story 16.1 documentation fixes are complete. The script verifies the CURRENT final state.

### Project Structure Notes

- `scripts/` directory does NOT exist yet — must be created
- All paths in the script must be relative to project root (not absolute)
- The script reads `docs/infrastructure-metrics.md` for documented values and compares against actual files
- No existing files are modified — this story is purely additive

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic 16, Story 16.2]
- [Source: _bmad-output/planning-artifacts/prd.md#FR31, FR32]
- [Source: _bmad-output/planning-artifacts/architecture.md#Documentation Metrics File Pattern (B-19)]
- [Source: _bmad-output/planning-artifacts/prd.md#NFR14]
- [Source: _bmad-output/implementation-artifacts/16-1-create-single-source-infrastructure-metrics-file.md#Dev Notes]
- [Source: docs/infrastructure-metrics.md]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (claude-opus-4-6)

### Debug Log References

- Initial `grep -cE` patterns with `$` anchor failed on CRLF files (YAML templates have Windows line endings). Fixed by using `-cP` without `$` anchor.
- `FunctionName:` grep overcounted Lambda functions (matched permissions/references too). Fixed by counting `AWS::Lambda::Function` resource type instead.
- Script file itself needed CRLF→LF conversion after creation on Windows filesystem (WSL mounted NTFS).

### Completion Notes List

- Created `scripts/verify-documentation-metrics.sh` — bash script that reads documented counts from `docs/infrastructure-metrics.md` and compares against 8 actual infrastructure metrics.
- Script checks: Flask endpoints (19), api-gw-app paths (11), api-gw-infra paths (7), url-add paths (1), Lambda total (12 = 10 CF + 2 non-CF), CF-managed Lambdas (10), deploy.ini templates (26), total .yaml template files (33).
- All 8 checks pass with exit code 0. Failure detection verified (exit code 1 with FAIL output). Missing file handling verified (clear error message + exit 1).
- Script is CI-friendly: no colors, no interactive prompts, deterministic exit codes.
- Handles CRLF files transparently (common in WSL/Windows environments).
- No Python code modified, no existing tests affected — purely additive story.

### Change Log

- 2026-02-21: Created `scripts/` directory and `scripts/verify-documentation-metrics.sh` verification script (Story 16.2)
- 2026-02-21: Code review — fixed 3 issues (H1: deploy.ini section scope, M1: error handling for count extraction, M2: B-3 dependency comment)

### File List

- `scripts/verify-documentation-metrics.sh` [NEW] — Documentation drift verification script
- `_bmad-output/implementation-artifacts/16-2-create-automated-documentation-drift-verification-script.md` [MODIFIED] — Story file updated with completion status and review notes
- `_bmad-output/implementation-artifacts/sprint-status.yaml` [MODIFIED] — Story status updated to review

### Senior Developer Review (AI)

**Reviewer:** Claude Opus 4.6 | **Date:** 2026-02-21

**Review Outcome:** Approved with fixes applied

**Findings (3 fixed, 2 low accepted):**

| # | Severity | Issue | Resolution |
|---|----------|-------|------------|
| H1 | HIGH | `deploy.ini` grep counted ALL sections, not just `[dev]` — will break when `[prod]`/`[qa]` added | **Fixed:** Replaced `grep` with `awk` state machine extracting only `[dev]` section |
| M1 | MEDIUM | Documented count extraction had no error handling — cryptic abort on format changes | **Fixed:** Added `extract_documented()` helper with `|| true` and meaningful error messages |
| M2 | MEDIUM | Hardcoded `lenie_2_` Lambda pattern conflicts with backlog B-3 rename | **Fixed:** Added NOTE comment documenting B-3 dependency |
| L1 | LOW | No `set -o pipefail` | Accepted — current pipelines handle 0-match case correctly |
| L2 | LOW | No explicit project-root check | Accepted — `check_file_exists` already catches wrong directory |

**Post-fix verification:** 8/8 checks pass, exit code 0.
