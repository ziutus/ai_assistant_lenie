# Story 13.1: Add Deployment Safety Header to zip_to_s3.sh

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **developer**,
I want to see the target AWS account, profile, environment, and S3 bucket before any deployment proceeds,
so that I can verify I'm deploying to the correct account and abort if something looks wrong.

## Acceptance Criteria

1. **Given** the developer runs `infra/aws/serverless/zip_to_s3.sh`
   **When** the script sources the env file (`env.sh` or `env_lenie_2025.sh`)
   **Then** the script displays: sourced env file name, AWS account ID, AWS profile, environment, and S3 bucket name
   **And** the info is displayed before any S3 upload or Lambda update occurs

2. **Given** the deployment info is displayed
   **When** the developer reviews the information
   **Then** the script prompts for confirmation (`Continue with deployment? (y/N)`)
   **And** the developer can abort by pressing Enter or typing `n`/`N`

3. **Given** the developer passes `--yes` or `-y` flag
   **When** the script runs
   **Then** the confirmation prompt is skipped (for automation)
   **And** the deployment info is still displayed

4. **Given** `env.sh` is sourced (default)
   **When** the script displays account info
   **Then** account `008971653395` and profile `default` are shown

5. **Given** `env_lenie_2025.sh` is sourced instead
   **When** the script displays account info
   **Then** account `049706517731` and profile `lenie-ai-2025-admin` are shown

## Tasks / Subtasks

- [x] Task 1: Add `--yes`/`-y` flag parsing before existing argument handling (AC: #3)
  - [x] 1.1: Parse flags from `$@` before extracting positional `$1` (functions_type)
  - [x] 1.2: Set `AUTO_CONFIRM=false` as default, flip to `true` on `--yes`/`-y`
- [x] Task 2: Add deployment info header display after env sourcing and function list loading (AC: #1, #4, #5)
  - [x] 2.1: Display sourced env file name (currently hardcoded `./env.sh` on line 5)
  - [x] 2.2: Display `AWS_ACCOUNT_ID`, `PROFILE`, `ENVIRONMENT`, `AWS_S3_BUCKET_NAME`
  - [x] 2.3: Insert block at line 28 (after `echo "function list: $FUNCTION_LIST"`, before `TMP_DIR="tmp"`)
- [x] Task 3: Add confirmation prompt after info header (AC: #2, #3)
  - [x] 3.1: Use `read -p "Continue with deployment? (y/N) "` pattern
  - [x] 3.2: Default to abort (N) — only proceed on explicit `y`/`Y`
  - [x] 3.3: Skip prompt when `AUTO_CONFIRM=true`

## Dev Notes

### Target File

`infra/aws/serverless/zip_to_s3.sh` — 87 lines, bash script with `set -e`.

### Current Script Flow

```
Line 1-2:   Shebang + set -e
Line 5:     source ./env.sh (hardcoded)
Line 8-12:  Argument validation (requires $1: 'simple' or 'app')
Line 14-23: Set FUNCTION_LIST_FILE based on $1
Line 25:    Load function list from file
Line 27:    Echo function list
Line 29-31: Create tmp dir, cd into it
Line 39-83: Main loop: package + upload + update each Lambda
Line 85-86: Exit 0
```

### Critical: Argument Handling with Flags

The script currently uses `$1` directly for `functions_type`. Adding `--yes`/`-y` flags requires filtering them from positional arguments. Pattern:

```bash
AUTO_CONFIRM=false
POSITIONAL_ARGS=()
for arg in "$@"; do
  case "$arg" in
    --yes|-y) AUTO_CONFIRM=true ;;
    *) POSITIONAL_ARGS+=("$arg") ;;
  esac
done
set -- "${POSITIONAL_ARGS[@]}"
```

This must go **before** the `if [ $# -eq 0 ]` check on line 8, so `$1` correctly refers to `functions_type` after flags are stripped.

### Info Display Insertion Point

Insert after line 27 (`echo "function list: $FUNCTION_LIST"`) and before line 29 (`TMP_DIR="tmp"`). At this point all variables are available:
- `AWS_ACCOUNT_ID` — from sourced env file
- `PROFILE` — from sourced env file
- `ENVIRONMENT` — from sourced env file
- `AWS_S3_BUCKET_NAME` — from sourced env file
- `FUNCTIONS_TYPE` — from positional argument

### Env File Name Display

The script hardcodes `source ./env.sh` on line 5. The env file name is not stored in a variable. Options:
1. **Simple approach (recommended):** Add `ENV_FILE="./env.sh"` before the source line, then `source "$ENV_FILE"`. Display `$ENV_FILE` in the header.
2. The developer manually changes line 5 to source a different file — this is the existing workflow per `infra/aws/serverless/CLAUDE.md`.

### Architecture Pattern to Follow

From `_bmad-output/planning-artifacts/architecture.md` — Sprint 4 Bash Script Modification Pattern:

**Info display block:**
```bash
echo "================================================"
echo "  Deployment Target Information"
echo "================================================"
echo "  Env file:    ${ENV_FILE}"
echo "  AWS Account: ${AWS_ACCOUNT_ID}"
echo "  Profile:     ${PROFILE}"
echo "  Environment: ${ENVIRONMENT}"
echo "  S3 Bucket:   ${AWS_S3_BUCKET_NAME}"
echo "================================================"
```

**Confirmation prompt:**
```bash
if [ "$AUTO_CONFIRM" != "true" ]; then
  read -p "Continue with deployment? (y/N) " confirm
  if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
    echo "Deployment cancelled."
    exit 0
  fi
fi
```

### Anti-Patterns (DO NOT)

- Do NOT add colored output (no colors in existing scripts)
- Do NOT restructure the existing loop or variable handling
- Do NOT add logging to file
- Do NOT change the existing `set -e` behavior
- Do NOT add new dependencies or external tools
- Do NOT modify the Lambda packaging or upload logic

### Environment Variables Reference

| Variable | env.sh (008971653395) | env_lenie_2025.sh (049706517731) |
|----------|----------------------|----------------------------------|
| `PROFILE` | `default` | `lenie-ai-2025-admin` |
| `AWS_ACCOUNT_ID` | `008971653395` | `049706517731` |
| `AWS_S3_BUCKET_NAME` | `lenie-dev-cloudformation` | `lenie-2025-dev-cloudformation` |
| `ENVIRONMENT` | `dev` | `dev` |
| `PROJECT_NAME` | `lenie` | `lenie` |

### Testing

- Run `./zip_to_s3.sh simple` — verify header displays, prompt appears, abort on Enter
- Run `./zip_to_s3.sh --yes simple` — verify header displays, no prompt, deployment proceeds
- Run `./zip_to_s3.sh -y app` — verify flag works with both argument positions
- Run `./zip_to_s3.sh simple --yes` — verify flag works regardless of position
- Manually change source to `env_lenie_2025.sh` — verify account `049706517731` is shown

### Project Structure Notes

- File location: `infra/aws/serverless/zip_to_s3.sh` — single file modification
- No new files created
- No changes to `env.sh` or `env_lenie_2025.sh` (AWS_ACCOUNT_ID already exists in both)
- No changes to function list files or Lambda code

### References

- [Source: _bmad-output/planning-artifacts/architecture.md#Sprint 4 — Bash Script Modification Pattern]
- [Source: _bmad-output/planning-artifacts/epics.md#Story 13.1]
- [Source: _bmad-output/planning-artifacts/prd.md#B-11: Add AWS Account Info to zip-to-s3 Script]
- [Source: infra/aws/serverless/CLAUDE.md#Deployment Scripts]
- [Source: infra/aws/serverless/zip_to_s3.sh — current implementation]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

No issues encountered.

### Completion Notes List

- Implemented `--yes`/`-y` flag parsing using positional argument filtering pattern (for/case loop with `set --` reassignment), placed before the existing `$#` check so `$1` correctly refers to `functions_type` after flags are stripped.
- Replaced hardcoded `source ./env.sh` with `ENV_FILE="./env.sh"; source "$ENV_FILE"` so the env file name can be displayed in the info header.
- Added deployment info header block displaying ENV_FILE, AWS_ACCOUNT_ID, PROFILE, ENVIRONMENT, and AWS_S3_BUCKET_NAME — inserted after function list echo and before TMP_DIR creation.
- Added confirmation prompt with default-abort behavior (`y/N`), skipped when `AUTO_CONFIRM=true`.
- Bash syntax validation passed (`bash -n`).
- No automated tests applicable — this is a bash deployment script with no existing test framework (bats). Manual testing scenarios documented in Dev Notes.

### Change Log

- 2026-02-19: Implemented all 3 tasks — flag parsing, info header display, confirmation prompt. Single file modified.
- 2026-02-19: Code review fixes — added env var validation guard, updated usage message with flag documentation.
- 2026-02-20: Second code review fixes — extended env var validation to include ENVIRONMENT and PROJECT_NAME, fixed architecture.md anti-pattern note.

### File List

- `infra/aws/serverless/zip_to_s3.sh` (modified) — added flag parsing, ENV_FILE variable, deployment info header, confirmation prompt, env var validation, updated usage message
- `_bmad-output/planning-artifacts/architecture.md` (modified) — fixed incorrect set -e anti-pattern note in Bash Script Modification Pattern

## Senior Developer Review (AI)

**Reviewer:** Claude Opus 4.6 | **Date:** 2026-02-19

**Findings Summary:** 0 Critical, 0 High, 2 Medium (fixed), 2 Low (accepted)

**Fixed Issues:**
- [M1] Usage message updated to document `--yes`/`-y` flags (line 27-29)
- [M2] Added env var validation guard after source — prevents deploying with blank account info (lines 8-12)

**Accepted/Deferred Issues:**
- [L1] Flag parsing placed after source (architecture pattern recommends before) — functionally correct, no impact
- [L2] No `--help`/`-h` flag — standard convention but out of scope for this story

**Verdict:** All 5 Acceptance Criteria verified against implementation. All tasks genuinely complete. Code review passed after fixes.

### Senior Developer Review #2 (AI)

**Reviewer:** Claude Opus 4.6 | **Date:** 2026-02-20

**Findings Summary:** 0 Critical, 0 High, 2 Medium (fixed), 2 Low (accepted)

**Fixed Issues:**
- [M1] Extended env var validation guard to include ENVIRONMENT and PROJECT_NAME — both used in Lambda naming (line 86) but were missing from the safety check
- [M2] Fixed architecture.md anti-pattern note: changed "Adding `set -e` (existing script does not use it)" to "Changing the existing `set -e` behavior" — script HAS set -e at line 2

**Accepted/Deferred Issues:**
- [L1] Variable naming inconsistency: architecture uses `${ENV_FILE_NAME}`, implementation uses `${ENV_FILE}` — cosmetic, no functional impact
- [L2] Pre-existing `--profile` inconsistency: S3 upload (line 115) uses default profile, Lambda update (line 118) uses explicit `${PROFILE}` — out of scope for this story

**Verdict:** All 5 Acceptance Criteria re-verified. Both Medium issues fixed. Story remains done.
