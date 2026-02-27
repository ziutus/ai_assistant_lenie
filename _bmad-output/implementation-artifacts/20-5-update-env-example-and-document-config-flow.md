# Story 20.5: Update .env_example and Document Config Flow

Status: done

## Story

As a **developer**,
I want `.env_example` to reflect the new bootstrap-only structure and clear documentation of the secrets management flow,
so that future developers understand how configuration works in each environment and cannot accidentally leak secrets via misconfigured `.env` files.

## Acceptance Criteria

1. **Given** `.env_example` currently lists all configuration variables **When** the developer updates it **Then** it contains only bootstrap variables: `SECRETS_BACKEND`, `SECRETS_ENV`, `PROJECT_CODE`, `VAULT_ADDR`, `VAULT_TOKEN`, `AWS_REGION`, `ENV_DATA` **And** each variable has a comment explaining its purpose and which backends use it **And** a header comment explains the three backends (`env`, `vault`, `aws`) and points to documentation.

2. **Given** the developer documents the new config flow **When** documentation is written **Then** `docs/secrets-management.md` is created covering: architecture overview, Vault setup (Docker/NAS), AWS SSM/Secrets Manager setup, variable classification (secret vs config), adding new variables, troubleshooting.

3. **Given** the migration is complete **When** the developer verifies the setup **Then** Docker Compose `compose.yaml` documents that when using vault/aws backend `.env` should contain only bootstrap vars **And** `.env_example` reflects bootstrap-only structure **And** legacy variable reference is preserved in generated output (`generate env-example --backend env`).

4. **Given** CLAUDE.md has an Environment Variables section **When** the developer updates it **Then** the section references `docs/secrets-management.md` for full details and mentions the `generate env-example` tool for generating backend-specific env files.

## Tasks / Subtasks

- [x] Task 1: Update `.env_example` to bootstrap-only structure (AC: #1)
  - [x] 1.1 Replace current `.env_example` content with bootstrap-only variables from `scripts/vars-classification.yaml` bootstrap group
  - [x] 1.2 Add header explaining three backend modes (`env`, `vault`, `aws`) with pointer to `docs/secrets-management.md`
  - [x] 1.3 Add inline comments explaining which backends require which bootstrap vars
  - [x] 1.4 Add footer note: "For SECRETS_BACKEND=env, generate full .env with: `python scripts/env_to_vault.py generate env-example --backend env --output .env`"

- [x] Task 2: Create `docs/secrets-management.md` documentation (AC: #2)
  - [x] 2.1 Write architecture overview section — three backends, bootstrap vs application vars, config_loader flow
  - [x] 2.2 Write Vault setup section — NAS Docker, VAULT_ADDR, VAULT_TOKEN, KV v2 path convention (`secret/{project_code}/{env}`), auto-unseal via AWS KMS
  - [x] 2.3 Write AWS SSM setup section — SSM path convention (`/{project_code}/{env}/{key}`), SecureString, IAM requirements, Lambda VPC constraints
  - [x] 2.4 Write variable classification section — reference `scripts/vars-classification.yaml` as SSOT, explain secret vs config types
  - [x] 2.5 Write "Adding new variables" section — update YAML, upload to backends, verify with `compare` command
  - [x] 2.6 Write troubleshooting section — common errors (missing VAULT_TOKEN, SSM path not found, backend unreachable)
  - [x] 2.7 Write env_to_vault.py tooling section — document compare, review, remove, generate, validate commands

- [x] Task 3: Update `infra/docker/compose.yaml` with documentation comment (AC: #3)
  - [x] 3.1 Add YAML comment above `env_file: .env` explaining that for vault/aws backends `.env` should contain only bootstrap vars

- [x] Task 4: Update `CLAUDE.md` Environment Variables section (AC: #4)
  - [x] 4.1 Simplify Environment Variables section — keep bootstrap vars description, add reference to `docs/secrets-management.md`
  - [x] 4.2 Add mention of `scripts/env_to_vault.py generate env-example` tool for generating backend-specific env files

- [x] Task 5: Verify end-to-end consistency (AC: #1, #2, #3, #4)
  - [x] 5.1 Run `python scripts/env_to_vault.py generate env-example --backend env` and verify output matches current variable set in YAML
  - [x] 5.2 Validate `.env_example` contains only bootstrap variables
  - [x] 5.3 Verify all cross-references between docs are correct (CLAUDE.md → secrets-management.md → vars-classification.yaml)

## Dev Notes

### Architecture Context

The config_loader module (`backend/library/config_loader.py`) was created in Story 20-1 and integrated in Story 20-4. It provides:
- `Config` class (dict subclass with `require()` method)
- Three backends: `EnvBackend`, `VaultBackend`, `AWSSSMBackend`
- Singleton pattern via `get_config()` / `load_config()`
- Backward compatibility: non-env backends inject values into `os.environ` so library modules using `os.getenv()` still work

Bootstrap vars (always from real environment): `SECRETS_BACKEND`, `VAULT_ADDR`, `VAULT_TOKEN`, `SECRETS_ENV`, `VAULT_ENV` (deprecated), `ENV_DATA`, `AWS_REGION`, `PROJECT_CODE`

### Story 20-6 Provides Key Tooling

Story 20-6 (already done) created `scripts/vars-classification.yaml` — the Single Source of Truth for all ~50 config variables. It also added `generate env-example` command to `env_to_vault.py`. **This story should USE that tooling, not recreate it.**

Relevant commands from env_to_vault.py:
- `python scripts/env_to_vault.py generate env-example --backend vault` — generate .env for vault backend (bootstrap only)
- `python scripts/env_to_vault.py generate env-example --backend env --output .env_example` — generate full .env for env backend
- `python scripts/env_to_vault.py validate env-file --backend vault` — validate .env has correct vars for backend
- `python scripts/env_to_vault.py compare ...` — compare variable state between backends

### Current State of Files

**`.env_example`** (current): Has partial bootstrap header from Story 20-4 code review, but still lists ALL application variables below. Needs trimming to bootstrap-only.

**`infra/docker/compose.yaml`**: Uses `env_file: .env` for lenie-ai-server. This works for all backends — the .env content changes, not the compose.yaml structure. When `SECRETS_BACKEND=vault`, .env only needs bootstrap vars; when `SECRETS_BACKEND=env`, .env needs everything.

**`CLAUDE.md`**: Environment Variables section at line ~155 already documents SECRETS_BACKEND, SECRETS_ENV, PROJECT_CODE, ENV_DATA, and key app vars. Needs pointer to new docs.

**`docs/secrets-management.md`**: Does not exist yet — to be created.

### Compose.yaml Design Decision

Docker Compose does not support conditional env_file. The `env_file: .env` directive stays as-is. The difference is in `.env` file content:
- `SECRETS_BACKEND=env`: .env has ALL variables (generated via `generate env-example --backend env`)
- `SECRETS_BACKEND=vault`: .env has only bootstrap vars + VAULT_ADDR + VAULT_TOKEN
- `SECRETS_BACKEND=aws`: .env has only bootstrap vars + AWS_REGION

A YAML comment in compose.yaml will explain this.

### Testing Notes

This story is documentation-focused. Tests to run:
- Validate `.env_example` bootstrap-only content manually
- Run `python scripts/env_to_vault.py generate env-example --backend vault` to verify it produces similar content
- Verify markdown links in all docs are correct
- Run `ruff check` on any Python changes (none expected)

### Previous Story Learnings (Epic 20)

- Story 20-4 established the pattern of `cfg = load_config()` at module top level with `cfg.require()` for mandatory vars
- Story 20-4 code review (commit 63c271e) cleaned up .env_example header — build on that work
- Story 20-6 created vars-classification.yaml with comprehensive variable metadata — use it as the source for documentation
- Lambda VPC constraint: sqs-to-rds Lambda keeps CF env vars because it cannot reach SSM without NAT Gateway (document this edge case)

### Project Structure Notes

- `.env_example` — project root
- `docs/secrets-management.md` — new file in docs/
- `infra/docker/compose.yaml` — existing file
- `CLAUDE.md` — project root
- `scripts/vars-classification.yaml` — existing SSOT (read-only for this story)
- `scripts/env_to_vault.py` — existing tool (read-only for this story)
- `backend/library/config_loader.py` — existing module (read-only for this story)

### References

- [Source: `backend/library/config_loader.py`] — Config, backends, factory, singleton
- [Source: `scripts/vars-classification.yaml`] — Variable SSOT with groups, types, descriptions
- [Source: `scripts/env_to_vault.py`] — CLI tool with generate/validate commands
- [Source: `infra/docker/compose.yaml`] — Docker Compose configuration
- [Source: `.env_example`] — Current env example (to be replaced)
- [Source: `CLAUDE.md#Environment Variables`] — Current env var documentation (to be updated)
- [Source: `_bmad-output/planning-artifacts/epics/epic-20.md#Story 20.5`] — Epic definition

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

No debug issues encountered. Documentation-only story with no Python code changes.

### Completion Notes List

- Task 1: Replaced `.env_example` with bootstrap-only structure (7 bootstrap vars: SECRETS_BACKEND, SECRETS_ENV, PROJECT_CODE, ENV_DATA, VAULT_ADDR, VAULT_TOKEN, AWS_REGION). Header explains three backend modes and points to docs/secrets-management.md. Footer explains `generate env-example` command.
- Task 2: Created comprehensive `docs/secrets-management.md` (~200 lines) covering: architecture overview with config_loader flow diagram, Vault setup (KV v2 path convention, auto-unseal), AWS SSM setup (path convention, SecureString, Lambda VPC constraint), variable classification (secret vs config types, 9 groups from YAML), adding new variables workflow, troubleshooting (5 common error scenarios), env_to_vault.py tooling reference (all commands documented).
- Task 3: Added 3-line YAML comment above `env_file: .env` in compose.yaml explaining bootstrap-only .env for vault/aws backends and pointing to docs.
- Task 4: Simplified CLAUDE.md Environment Variables section — lists only bootstrap vars, references docs/secrets-management.md for full details, mentions `generate env-example` tool.
- Task 5: Verified end-to-end consistency — `generate env-example --backend env` produces full variable set from YAML, `--backend vault` produces bootstrap-only. Cross-references verified: CLAUDE.md→secrets-management.md, .env_example→secrets-management.md, compose.yaml→secrets-management.md, secrets-management.md→vars-classification.yaml. Ruff linting: no regressions. Unit tests: 60 passed, 6 pre-existing failures (unrelated).

### Change Log

- 2026-02-27: Story 20-5 implementation complete — .env_example trimmed to bootstrap-only, docs/secrets-management.md created, compose.yaml documented, CLAUDE.md updated with config_loader references.
- 2026-02-27: Code review fixes (3M + 4L) — removed incorrect `--write` flag from `set` command examples, replaced `sk-...` placeholder with `<your-openai-api-key>` to avoid secret scanner false positives, added VAULT_ENV deprecated note to bootstrap list, added TOC, added Env Backend Setup section, added "used by" annotations to .env_example bootstrap vars.

### File List

- `.env_example` — **modified**: replaced full variable list with bootstrap-only structure + header/footer documentation
- `docs/secrets-management.md` — **new**: comprehensive secrets management documentation
- `infra/docker/compose.yaml` — **modified**: added YAML comment explaining .env content per backend
- `CLAUDE.md` — **modified**: simplified Environment Variables section with reference to docs/secrets-management.md
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — **modified**: story status ready-for-dev → in-progress → review
- `_bmad-output/implementation-artifacts/20-5-update-env-example-and-document-config-flow.md` — **modified**: tasks marked complete, Dev Agent Record filled
