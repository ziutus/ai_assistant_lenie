# Story 31.1: Add Business Source License 1.1 to Repository

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **project owner**,
I want to add a Business Source License 1.1 (BSL 1.1) to the repository,
so that the project is protected from unauthorized commercial use by cloud providers while remaining open for community use and automatically converting to a permissive open-source license after a defined period.

## Acceptance Criteria

1. **Given** the repository has no LICENSE file, **when** BSL 1.1 is added, **then** a `LICENSE` file exists in the repository root containing the full BSL 1.1 text.
2. **Given** the BSL 1.1 license is applied, **when** a cloud provider attempts to offer the software as a managed service, **then** the Additional Use Grant explicitly prohibits this use case (anti-cloud-provider clause).
3. **Given** the BSL 1.1 license includes a Change Date, **when** the Change Date is reached (4 years from initial commit), **then** the license automatically converts to Apache 2.0 (or MPL 2.0 — confirm with project owner).
4. **Given** the LICENSE file is created, **when** the project README is reviewed, **then** a license section/badge references BSL 1.1 with a brief explanation of the terms.
5. **Given** the BSL 1.1 license is applied, **when** any source file header is reviewed, **then** no per-file license headers are required (license applies at repository level via LICENSE file).

## Tasks / Subtasks

- [x] Task 1: Create LICENSE file with BSL 1.1 text (AC: #1, #2, #3)
  - [x] 1.1 Use the official BSL 1.1 template from MariaDB/Hashicorp examples
  - [x] 1.2 Fill in Licensor: Krzysztof Jozwiak
  - [x] 1.3 Fill in Licensed Work: "lenie-server-2025" with description
  - [x] 1.4 Fill in Additional Use Grant: explicitly prohibit offering as managed/hosted service (anti-cloud-provider clause)
  - [x] 1.5 Fill in Change Date: 2030-03-12
  - [x] 1.6 Fill in Change License: Apache License, Version 2.0
- [x] Task 2: Update README.md with license information (AC: #4)
  - [x] 2.1 Add "License" section to README.md referencing BSL 1.1
  - [x] 2.2 Briefly explain: what BSL 1.1 means, what the anti-cloud clause covers, when it converts to open-source

## Dev Notes

- **BSL 1.1** was created by MariaDB and is used by companies like HashiCorp (Terraform, Vault), Sentry, CockroachDB, and others to protect against cloud provider exploitation while keeping code source-available.
- The license is **not OSI-approved** — it is a "source-available" license, not "open-source" per OSI definition. This distinction should be noted in README.
- The **Additional Use Grant** is the key customizable clause — it defines what additional uses are permitted beyond non-production use. For Lenie, the restriction should focus on preventing cloud providers from offering it as a competing managed service.
- The **Change Date** triggers automatic conversion to a fully permissive license (Apache 2.0 or MPL 2.0). 4 years is a common choice (HashiCorp uses 4 years).
- No code changes required — this is a documentation/governance task only.
- The `shared_python/unified-config-loader/` package has its own identity but is part of this repo — BSL 1.1 at the repo root covers all contents.

### Project Structure Notes

- LICENSE file goes in the repository root (`/LICENSE`)
- README.md is in the repository root (`/README.md`)
- No per-file headers needed — single LICENSE file covers the entire repository
- No impact on build, CI/CD, or runtime behavior

### References

- [BSL 1.1 Official FAQ](https://mariadb.com/bsl-faq-mariadb/)
- [BSL 1.1 License Template](https://mariadb.com/bsl11/)
- [HashiCorp BSL adoption](https://www.hashicorp.com/license-faq) — reference for anti-cloud-provider clause wording
- [Source: sprint-status.yaml] — story 31-1-add-bsl-1-1-license definition
- [Source: CLAUDE.md] — project overview and structure

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

No debug issues encountered.

### Completion Notes List

- Created LICENSE file with full BSL 1.1 text. Licensor: Krzysztof Jozwiak. Licensed Work: lenie-server-2025. Additional Use Grant: anti-cloud-provider clause prohibiting managed/hosted/SaaS offerings. Change Date: 2030-03-12. Change License: Apache License 2.0.
- Added "License" section to README.md before "Supported Platforms" section. Explains BSL 1.1 terms, anti-cloud clause, Change Date, and notes it is source-available (not OSI open-source).
- No code changes — documentation/governance only. All existing tests pass (49 passed, 20 skipped).

### Senior Developer Review (AI)

- **Review Date:** 2026-03-12
- **Review Outcome:** Approve (after fixes)
- **Issues Found:** 0 High, 3 Medium, 1 Low — all fixed
- **Action Items:**
  - [x] M1: Added contact email (krzysztof@lenie-ai.eu) to LICENSE
  - [x] M2: Fixed copyright year to 2025-2026
  - [x] M3: Fixed README License section — production use is permitted (not restricted to non-production)
  - [x] L1: Added license reference to CLAUDE.md project overview line

### Change Log

- 2026-03-12: Created LICENSE (BSL 1.1) and updated README.md with license section.
- 2026-03-12: Code review fixes — added contact email, fixed copyright year, corrected README wording, added license to CLAUDE.md.

### File List

- LICENSE (new)
- README.md (modified)
- CLAUDE.md (modified)
- _bmad-output/implementation-artifacts/31-1-add-bsl-1-1-license.md (modified)
- _bmad-output/implementation-artifacts/sprint-status.yaml (modified)
