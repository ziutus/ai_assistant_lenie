# Story 13.2: Verify CRLF Git Config for Parameter Files

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **developer**,
I want to verify that all CloudFormation parameter files have correct LF line endings and `.gitattributes` enforces this,
so that the CRLF investigation from Sprint 3 is formally closed with documented findings.

## Acceptance Criteria

1. **Given** 29 parameter files exist in `infra/aws/cloudformation/parameters/dev/`
   **When** the developer checks line endings of all JSON parameter files
   **Then** all files have LF line endings (no CRLF)

2. **Given** `.gitattributes` exists in the repository root
   **When** the developer reviews its rules
   **Then** `*.json` files are covered with `text eol=lf` (or equivalent rule ensuring LF)

3. **Given** the verification is complete
   **When** the developer documents the result
   **Then** one of two outcomes is documented:
   - `.gitattributes` is updated with additional rules if current coverage is inadequate
   - Current config is confirmed adequate with explanation (referencing Sprint 3 Story 7-2 finding that CRLF warning was due to Windows `core.autocrlf`, not file content)

## Tasks / Subtasks

- [x] Task 1: Verify all 29 parameter files have LF line endings (AC: #1)
  - [x] 1.1: List all files in `infra/aws/cloudformation/parameters/dev/`
  - [x] 1.2: Check each file for CRLF bytes (`\r\n`) — use `file` command or `od`/`xxd` grep for `\r`
  - [x] 1.3: Report result: count of LF-only files vs CRLF files
- [x] Task 2: Verify `.gitattributes` coverage for JSON files (AC: #2)
  - [x] 2.1: Read `.gitattributes` from repository root
  - [x] 2.2: Confirm `*.json text eol=lf` rule exists
  - [x] 2.3: Confirm global `* text=auto eol=lf` rule exists as fallback
- [x] Task 3: Document verification result (AC: #3)
  - [x] 3.1: Add verification summary to `docs/development-guide.md` in the Line Endings section
  - [x] 3.2: Reference Sprint 3 Story 7-2 finding (CRLF warning was Windows `core.autocrlf`, not file content)
  - [x] 3.3: Confirm `.gitattributes` is adequate — no additional rules needed

## Dev Notes

### Context: Why This Story Exists

Sprint 3 Story 7-2 (remove-url-add2-endpoint) encountered a CRLF git warning when committing CloudFormation parameter files. Investigation revealed:
- The warning was caused by Windows `core.autocrlf=true` setting interacting with files that had no `.gitattributes` enforcement
- The actual file content was not corrupt — the warning was about git's line-ending conversion
- `.gitattributes` was subsequently added (commit `6a9bfd7`) with comprehensive LF enforcement rules
- Parameter files were normalized (commit `88b833e`)

This story formally closes the B-12 backlog item by verifying the fix is complete and documenting the findings.

### Pre-Existing Work (Already Done)

Most of the technical work has already been completed:

1. **`.gitattributes` created** (commit `6a9bfd7`): Contains `* text=auto eol=lf` (global rule) AND `*.json text eol=lf` (explicit JSON rule). Both cover parameter files.

2. **Line endings normalized** (commit `88b833e`): Commit message says "normalize CRLF line endings in CF parameter files (B-12)".

3. **Documentation written** (`docs/development-guide.md`): Line Endings section documents `.gitattributes` purpose, how it works, and how to fix existing working copies.

### What The Dev Agent Must Do

This is a **verification task**, not a code change task. The dev agent should:

1. **Run a verification command** to confirm all 29 parameter files in `infra/aws/cloudformation/parameters/dev/` have LF endings. Example commands:
   ```bash
   # Check for CRLF in parameter files (should return nothing)
   grep -rPl '\r' infra/aws/cloudformation/parameters/dev/

   # Or use file command to check line endings
   file infra/aws/cloudformation/parameters/dev/*.json
   ```

2. **Confirm `.gitattributes` rules** — already verified: line 2 (`* text=auto eol=lf`) and line 18 (`*.json text eol=lf`)

3. **Document the verification** — add a brief note to `docs/development-guide.md` confirming B-12 investigation is closed, or add the verification date to existing documentation.

### File Inventory: Parameter Files to Check

29 JSON files in `infra/aws/cloudformation/parameters/dev/`:
- All follow standard CloudFormation parameter file format
- All should have LF line endings after `.gitattributes` enforcement

### Current `.gitattributes` Rules (Relevant)

```
# Line 2 — global rule
* text=auto eol=lf

# Line 18 — explicit JSON rule
*.json text eol=lf
```

Both rules ensure JSON parameter files use LF line endings. The explicit `*.json` rule is redundant (global rule covers it) but provides defense-in-depth and explicit documentation of intent.

### Expected Outcome

**Result: Current configuration is adequate — no changes needed.**

Rationale:
- `.gitattributes` already enforces LF for `*.json` files (both global and explicit rules)
- Parameter files were already normalized in commit `88b833e`
- Sprint 3 Story 7-2 root cause was Windows `core.autocrlf`, which `.gitattributes` overrides
- `docs/development-guide.md` already documents line endings comprehensively

### Anti-Patterns (DO NOT)

- Do NOT make changes to `.gitattributes` unless verification reveals missing coverage
- Do NOT modify parameter file content (only check line endings)
- Do NOT run `git add --renormalize .` unless verification shows CRLF files exist
- Do NOT add complex scripts or CI checks for this verification — this is a one-time closure task

### Project Structure Notes

- `.gitattributes` — repository root, already comprehensive
- `infra/aws/cloudformation/parameters/dev/` — 29 JSON files, all should be LF
- `docs/development-guide.md` — Line Endings section already exists (lines 224-272)
- No new files needed
- Minimal or no file modifications expected

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 13.2]
- [Source: _bmad-output/planning-artifacts/prd.md#B-12: Fix CRLF Git Config for Parameter Files]
- [Source: _bmad-output/planning-artifacts/architecture.md#Sprint 4 — CRLF Verification (FR26-FR28)]
- [Source: .gitattributes — repository root]
- [Source: docs/development-guide.md#Line Endings (.gitattributes)]
- [Source: Commit 88b833e — normalize CRLF line endings in CF parameter files (B-12)]
- [Source: Commit 6a9bfd7 — feat: add AWS smoke test for URL add flow and .gitattributes]

### Previous Story Intelligence (Story 13.1)

Story 13.1 (Add Deployment Safety Header) completed successfully:
- Single file modification: `infra/aws/serverless/zip_to_s3.sh`
- Pattern: additive changes only, match existing script style
- Code review found 2 medium issues (both fixed): missing usage docs for flags, missing env var validation
- Learnings: keep bash script changes minimal, match existing style, validate variables exist before displaying

Relevant for 13.2: same minimal-change approach — verify and document, don't over-engineer.

### Git Intelligence

Recent commits relevant to this story:
- `88b833e` — `chore: normalize CRLF line endings in CF parameter files (B-12)` — direct B-12 work
- `6a9bfd7` — `feat: add AWS smoke test for URL add flow and .gitattributes` — added .gitattributes
- `07eda59` — `docs: add .gitattributes line endings documentation to development guide` — documented the rules

These 3 commits collectively address all technical aspects of B-12. This story is a formal verification closure.

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (claude-opus-4-6)

### Debug Log References

No issues encountered. All verification steps passed on first attempt.

### Completion Notes List

- **Task 1:** Verified all 29 JSON parameter files in `infra/aws/cloudformation/parameters/dev/` have LF line endings. `grep -rPl '\r'` returned no matches — 29/29 files are LF-only.
- **Task 2:** Confirmed `.gitattributes` has both `* text=auto eol=lf` (line 2, global fallback) and `*.json text eol=lf` (line 18, explicit JSON rule). Both rules cover parameter files adequately.
- **Task 3:** Added "Verification (B-12 Closure — Sprint 4, Story 13.2)" subsection to `docs/development-guide.md` in the Line Endings section. Documents verification result, references Sprint 3 Story 7-2 root cause (Windows `core.autocrlf`), and confirms `.gitattributes` is adequate with no additional rules needed.
- **Conclusion:** Current configuration is adequate. No changes to `.gitattributes` or parameter files were needed. This formally closes backlog item B-12.

### File List

- `docs/development-guide.md` — Modified: added verification subsection (B-12 closure) to Line Endings section

## Change Log

- 2026-02-20: Verified LF line endings for all 29 CF parameter files, confirmed `.gitattributes` coverage adequate, documented B-12 closure in development guide (Story 13.2)
- 2026-02-20: **Code Review (AI)** — Fixed 3 issues: (M2) removed fragile line number references to `.gitattributes` in documentation, (L1) added verification date, (M3) added `git check-attr` verification mention. Note: `docs/architecture-infra.md` has unrelated unstaged changes (cost optimization) — not part of this story.
