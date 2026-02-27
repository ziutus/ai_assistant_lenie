---
title: 'Extend env_to_vault.py with Compare, Review, and Variable Classification SSOT'
slug: 'env-to-vault-compare-review-classify'
created: '2026-02-27'
status: 'ready-for-dev'
stepsCompleted: [1, 2, 3, 4]
tech_stack:
  - Python 3.11
  - ruamel.yaml (round-trip YAML preserving comments and formatting)
  - hvac (HashiCorp Vault client, lazy-loaded)
  - boto3 (AWS SDK, lazy-loaded)
  - pytest + unittest.TestCase
files_to_modify:
  - scripts/env_to_vault.py (extend with 5 new commands + YAML loader + refactor dispatch)
  - scripts/vars-classification.yaml (new — SSOT for all config variables)
  - scripts/tests/test_env_to_vault.py (new — unit tests)
  - backend/pyproject.toml (add ruamel.yaml dependency)
code_patterns:
  - dry-run by default, --write to execute
  - lazy imports (_require_hvac, _require_boto3, new _require_ruamel)
  - mask_value() for secure display
  - argparse top-level commands registered like sync (no nested subcommands)
  - dispatch via if/elif chain for top-level commands
  - SKIP_VARS exclusion of bootstrap vars
  - cmd_sync() pattern for read-read-diff-display (reuse for compare)
  - vault delete = read-modify-write whole secret
  - ssm delete = direct per-key API call with ParameterNotFound handling
  - interactive input pattern: input("[y/N]: ").strip().lower() guarded by --write flag
test_patterns:
  - unittest.TestCase as base class, run via pytest
  - patch.dict(os.environ, {...}, clear=True) for env isolation
  - mock hvac/boto3 via sys.modules patching
  - no conftest.py, no shared fixtures
  - standalone scripts/tests/ directory
---

# Tech-Spec: Extend env_to_vault.py with Compare, Review, and Variable Classification SSOT

**Created:** 2026-02-27

## Overview

### Problem Statement

After migrating secrets to Vault and AWS SSM (Epic 20), there are no tools to compare state between backends, clean up unused keys, or manage the variable lifecycle. Configuration variable documentation is fragmented across 16+ files with ~14 variables completely undocumented. There is no Single Source of Truth for what variables exist, their classification (secret vs config), or which backends/environments use them.

### Solution

Extend `scripts/env_to_vault.py` with three new capabilities:

1. **`vars-classification.yaml`** — Single Source of Truth (SSOT) defining all configuration variables with classification, backend definitions, and environment mappings
2. **`compare` command** — universal comparison between any two sources (vault/ssm/env-file)
3. **`review` command** — interactive review of YAML-defined variables vs actual backend state (read-only display), with interactive actions (add orphans, delete variables)
4. **`remove` command** — remove a variable from all backends in an environment + YAML (replaces ambiguous `delete --everywhere`)
5. **`generate env-example`** — produce `.env_example` from YAML for a given backend type
6. **`validate env-file`** — check that `.env` contains only appropriate variables for the active backend
7. **Unit tests** for all new commands

### Scope

**In Scope:**

- Design and create `scripts/vars-classification.yaml` with full inventory of ~50 variables
- Named backend instances (e.g., `nas-vault`, `aws-ssm-main`, `aws-ssm-2025`) with connection metadata
- Per-environment backend mapping (`dev: [nas-vault, aws-ssm-main]`, `prod: [aws-ssm-2025]`)
- `compare --from {source} --to {source} --env ENV [--show-values]`
- `review --env ENV` — interactive review: read-only display (9a), then interactive actions (9b)
- `remove VAR --env ENV [--write]` — remove variable from all backends in environment + YAML
- `generate env-example --backend {vault|aws|env}` — produce `.env_example` from YAML
- `validate env-file --backend {vault|aws|env}` — check `.env` for excess variables
- `scripts/tests/test_env_to_vault.py` — unit tests for new commands

**Out of Scope:**

- Automatic generation of CLAUDE.md sections from YAML (manual for now)
- Changes to `config_loader.py` to read bootstrap vars from YAML (future direction, confirmed)
- K8s ConfigMap/Secret generation from YAML
- Migration to AWS Secrets Manager
- B-65 (empty string handling in Config.require)
- Story 20-5 (docs, .env_example cleanup) — partially addressed by `generate`

## Context for Development

### Codebase Patterns

- **Dry-run by default**: All write operations require explicit `--write` flag. This pattern MUST be followed for all new commands.
- **Lazy imports**: `_require_hvac()` and `_require_boto3()` load dependencies on demand. New YAML dependency should follow same pattern with `_require_yaml()`.
- **Masked output**: `mask_value(value)` shows first 3 chars + `***`. Used for all secret display.
- **SKIP_VARS**: Bootstrap variables excluded from uploads. Aligns with `_BOOTSTRAP_VARS` in `config_loader.py`.
- **Argparse structure**: Two-level subcommands (`vault upload`, `ssm list`). Top-level commands (`sync`) handled separately in dispatch. New commands follow appropriate level.
- **SSM tags**: All parameters tagged with `managed-by=env-to-vault-script`, `project=lenie`, `environment={env}`.
- **Path alignment**: Both `env_to_vault.py` and `config_loader.py` use identical path patterns: Vault `secret/{project_code}/{env}`, SSM `/{project_code}/{env}/{key}`.

### Files to Reference

| File | Purpose |
| ---- | ------- |
| `scripts/env_to_vault.py` | Main script to extend (709 lines, 11 commands) |
| `backend/library/config_loader.py` | Config loader with `_BOOTSTRAP_VARS` — path patterns must stay aligned |
| `backend/pyproject.toml` | Dependencies — add `ruamel.yaml` here |
| `.env_example` | Root env template (31 vars, outdated) |
| `infra/docker/nas.env.example` | NAS env template (38 vars, most complete current source) |
| `backend/tests/unit/test_config_loader.py` | Best example of mocking patterns (hvac, boto3, os.environ) |
| `_bmad-output/planning-artifacts/epics/epic-20.md` | Epic 20: Secrets Management context |
| `_bmad-output/planning-artifacts/backlog/index.md` | B-66: unit tests for env_to_vault.py |

### Technical Decisions

1. **YAML format: Option A (flat + derived defaults)** — `type: secret` implies `ssm_type: SecureString` and `k8s: Secret`; `type: config` implies `ssm_type: String` and `k8s: ConfigMap`. Explicit override only when needed.

2. **Named backend instances** — backends have descriptive names (e.g., `nas-vault`, `aws-ssm-main`) rather than generic type names, to distinguish between multiple instances of the same type (e.g., two AWS accounts).

3. **Backend connection details** — not duplicated in YAML. `connection_from` field documents which bootstrap vars are needed; actual connection uses existing code (`get_vault_client()`, `get_ssm_client()`).

4. **`env` file as source, not backend** — `.env` file is a valid source for `compare` but is NOT listed in `environments.backends[]`. `--everywhere` only targets remote backends (vault/ssm instances).

5. **`purge` dropped** — `review` (interactive) + `remove` (scripted) cover all purge use cases without a dedicated command.

6. **Future direction confirmed** — `config_loader.py` will eventually read `_BOOTSTRAP_VARS` from `vars-classification.yaml` instead of hardcoded `frozenset`. Not in this spec's scope.

7. **`ruamel.yaml` over `pyyaml`** (Party Mode decision — Winston) — `remove` and `review [a]` rewrite the YAML file. `pyyaml`'s `yaml.dump()` strips comments and reformats. Since `vars-classification.yaml` is SSOT that humans will also read and edit, round-trip preservation is essential. Use `ruamel.yaml` with `YAML(typ='rt')` for all YAML read/write operations.

8. **Argparse extension strategy** — new commands (`compare`, `review`, `remove`, `generate`, `validate`) registered at `backend_parsers` level like `sync`. Dispatch via extended if/elif chain. `remove` is a separate top-level command (NOT `delete --everywhere`) to avoid UX confusion with `vault delete` / `ssm delete`. (Party Mode decision — Winston: avoid two `delete` commands at different levels.)

9. **Interactive prompts** — `review` uses `input("[y/N]: ").strip().lower()` pattern. All destructive actions guarded by confirmation or `--write` flag. Accepts `y`/`yes` only (default=no).

10. **Client connection caching** (Party Mode decision — Winston) — `resolve_backend_client()` returns clients that are cached in a `_client_cache: dict[str, Any]` keyed by backend name. Commands like `review` and `remove` connect to multiple backends in one invocation — caching avoids redundant connections. Pattern follows `cmd_sync()` lines 536-546 but formalized.

## Implementation Plan

### Tasks

- [ ] Task 1: Add ruamel.yaml as explicit dependency
  - File: `backend/pyproject.toml`
  - Action: Add `ruamel.yaml>=0.18` to `[dependencies]`
  - Action: Run `uv lock` to update lock file
  - Notes: Chosen over pyyaml for round-trip YAML preservation (comments, formatting). Required because `remove` and `review [a]` rewrite the YAML file.

- [ ] Task 2: Create `vars-classification.yaml` with full variable inventory
  - File: `scripts/vars-classification.yaml` (new)
  - Action: Create YAML file with the following structure:
    - `metadata` section: `project_code: lenie`, `version: "1.0"`, `description`
    - `backends` section: define `nas-vault` (type: vault_kv2, mount: secret, path_pattern: `{project_code}/{env}`), `aws-ssm-main` (type: aws_ssm, path_pattern: `/{project_code}/{env}/{key}`, region: eu-central-1, profile: default), `aws-ssm-2025` (type: aws_ssm, path_pattern same, region: eu-central-1, profile: lenie-ai-2025-admin)
    - `environments` section: `dev: backends: [nas-vault, aws-ssm-main]`, `prod: backends: [aws-ssm-2025]`, `qa: backends: [aws-ssm-2025]`
    - `groups` section with all variables organized into: `bootstrap` (SECRETS_BACKEND, SECRETS_ENV, VAULT_ADDR, VAULT_TOKEN, VAULT_ENV, ENV_DATA, AWS_REGION, PROJECT_CODE), `database` (POSTGRESQL_HOST, POSTGRESQL_DATABASE, POSTGRESQL_USER, POSTGRESQL_PASSWORD, POSTGRESQL_PORT, POSTGRESQL_SSLMODE), `llm` (LLM_PROVIDER, OPENAI_API_KEY, OPENAI_ORGANIZATION, EMBEDDING_MODEL, AI_MODEL_SUMMARY), `aws` (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_S3_WEBSITE_CONTENT, AWS_S3_TRANSCRIPT, AWS_QUEUE_URL_ADD, AWS_FREE_TIER_ACCESS_KEY_ID, AWS_FREE_TIER_SECRET_ACCESS_KEY, AWS_FREE_TIER_REGION, AWS_FREE_TIER_PROFILE, AWS_FREE_TIER_VPN_SERVER), `app` (PORT, DEBUG, USE_SSL, USE_CACHE, BACKEND_TYPE, CACHE_DIR, STALKER_API_KEY, STALKER_AWS_API_URL, STALKER_AWS_API_KEY), `integrations` (ASSEMBLYAI, FIRECRAWL_API_KEY, LANGFUSE_HOST, LANGFUSE_SECRET_KEY, LANGFUSE_PUBLIC_KEY, CLOUDFERRO_SHERLOCK_KEY, SERPER_DEV_APIKEY, OPENROUTER_API_KEY), `media` (TRANSCRIPT_PROVIDER, YOUTUBE_DEFAULT_LANGUAGE), `gcp` (GCP_PROJECT_ID, GCP_LOCATION, GCP_FIRESTORE_PROJECT_ID, GCP_FIRESTORE_DATABASE)
  - Notes: Each variable has fields: `description`, `type` (secret|config), `required` (true|false) or `required_when` (conditional), `default` (optional), `example` (optional), `used_by` (list of deployment targets), `secrets_manager` (optional, for rotation candidates). Derived defaults: `type: secret` → `ssm_type: SecureString`, `k8s: Secret`; `type: config` → `ssm_type: String`, `k8s: ConfigMap`. Source data from `nas.env.example` (most complete) + `os.getenv()` scan from library code.

- [ ] Task 3: Add YAML loader infrastructure to `env_to_vault.py`
  - File: `scripts/env_to_vault.py`
  - Action: Add `_require_ruamel()` lazy import function (same pattern as `_require_hvac()` at line 82). Returns `ruamel.yaml.YAML(typ='rt')` instance for round-trip preservation.
  - Action: Add `load_classification(yaml_path=None)` function that:
    - Defaults `yaml_path` to `{script_dir}/vars-classification.yaml`
    - Reads and parses YAML using `ruamel.yaml` round-trip loader
    - Returns parsed data (ruamel CommentedMap, preserves comments)
    - Caches result (module-level `_classification_cache`)
    - On file not found: print clear error message and `sys.exit(1)`
    - On YAML parse error: print error with details and `sys.exit(1)`
  - Action: Add `save_classification(classification, yaml_path=None)` function that:
    - Writes YAML back using round-trip dumper (preserves comments and formatting)
    - Invalidates `_classification_cache`
  - Action: Add `_client_cache: dict[str, Any] = {}` module-level dict for connection pooling
  - Action: Add helper functions:
    - `get_backends_for_env(classification, env)` → returns list of backend dicts from `environments[env].backends` resolved against `backends` section. Raises clear error if `env` not defined in `environments` or if a backend name references undefined backend in `backends` section.
    - `get_all_variables(classification)` → returns flat dict of all variables across all groups, with group name attached
    - `get_bootstrap_variables(classification)` → returns dict of variables in `bootstrap` group only
    - `get_derived_ssm_type(var_def)` → returns explicit `ssm_type` if set, else derives from `type` field
    - `resolve_backend_client(backend_def, args)` → returns appropriate client (vault or ssm) based on backend `type` field, reusing existing `get_vault_client()` / `get_ssm_client()`. Caches clients in `_client_cache` keyed by backend name. Raises clear error for unknown backend types (e.g., `aws_secrets_manager` not yet supported).
    - `read_backend_data(backend_def, client, env)` → returns all key-value pairs from a backend, reusing `vault_read_all()` / `ssm_read_all()`. Returns `{}` for empty/non-existent backends (not an error).
  - Notes: Keep helpers pure functions where possible for testability. `resolve_backend_client` bridges named backends to existing connection code. `_client_cache` prevents redundant connections when `review` or `remove` iterates over multiple backends.

- [ ] Task 4: Refactor argparse dispatch to support new top-level commands
  - File: `scripts/env_to_vault.py`
  - Action: Add new top-level subparsers to `backend_parsers` (same level as `sync`):
    - `compare`: `--from` (required, string — backend name or "env"), `--to` (required, string), `--env` (required), `--show-values` (flag), `--env-file`, `--region`, `--profile`
    - `review`: `--env` (required), `--env-file`, `--region`, `--profile`
    - `remove`: positional `keys` (nargs="+"), `--env` (required), `--write` (flag), `--env-file`, `--region`, `--profile`. Help text: "Remove variable(s) from ALL backends in an environment + YAML. For single-backend deletion, use 'vault delete' or 'ssm delete'."
    - `generate`: subparsers for `env-example` with `--backend` (required, choices: vault|aws|env), `--output` (optional, default stdout)
    - `validate`: subparsers for `env-file` with `--backend` (required, choices: vault|aws|env), `--env-file`
  - Action: Extend dispatch block (lines 686–704) with elif chain:
    ```python
    if args.backend == "sync":
        cmd_sync(args)
    elif args.backend == "compare":
        cmd_compare(args)
    elif args.backend == "review":
        cmd_review(args)
    elif args.backend == "remove":
        cmd_remove(args)
    elif args.backend == "generate":
        cmd_generate(args)
    elif args.backend == "validate":
        cmd_validate(args)
    else:
        commands[(args.backend, args.command)](args)
    ```
  - Notes: `remove` is a distinct command name from `vault delete`/`ssm delete` — no UX confusion. Existing `vault delete`/`ssm delete` remain unchanged and dispatch via the `commands` dict.

- [ ] Task 5: Implement `compare` command
  - File: `scripts/env_to_vault.py`
  - Action: Add `cmd_compare(args)` function based on `cmd_sync()` pattern (lines 509–602):
    - Read `--from` source: if value matches a backend name in YAML → connect via `resolve_backend_client()` and read data. If value is "env" → `parse_env_file(args.env_file)`.
    - Read `--to` target: same logic.
    - Compute diff: `only_source = sorted(set(source) - set(target))`, `only_target = sorted(set(target) - set(source))`, `different = sorted(k for k in source if k in target and source[k] != target[k])`, `in_sync = sorted(k for k in source if k in target and source[k] == target[k])`
    - Display grouped results:
      ```
      Comparing: nas-vault → aws-ssm-main (env: dev)

      Only in nas-vault (3):
        + JENKINS_URL = Jen***
        + OLD_VAR = old***
        + TEMP_KEY = tem***

      Only in aws-ssm-main (1):
        + NEW_SSM_VAR = new***

      Different values (2):
        ~ PORT = 500*** → 808***
        ~ DEBUG = Tru*** → fal***

      In sync: 45 keys
      ```
    - If `--show-values`: display full unmasked values (with warning header)
    - If no differences: `"Sources are identical (48 keys in sync)."`
  - Notes: No `--write` flag — compare is always read-only. Values masked by default using `mask_value()`.

- [ ] Task 6: Implement `generate env-example` command
  - File: `scripts/env_to_vault.py`
  - Action: Add `cmd_generate(args)` function:
    - Load classification YAML
    - Based on `--backend` argument:
      - `vault`: output only `bootstrap` group variables
      - `aws`: output only `bootstrap` group variables minus VAULT_ADDR, VAULT_TOKEN, VAULT_ENV
      - `env`: output ALL variables from all groups
    - Output format: standard `.env` style with group headers as comments:
      ```
      # Generated by env_to_vault.py from vars-classification.yaml
      # Backend: vault
      # Date: 2026-02-27

      # --- bootstrap ---
      # Secret backend to use (env | vault | aws)
      SECRETS_BACKEND="vault"
      # Environment name (dev | prod | qa)
      SECRETS_ENV=""
      # HashiCorp Vault server URL
      VAULT_ADDR=""
      ...
      ```
    - Use `example` value if set in YAML, else `default` value, else empty string
    - If `--output` specified: write to file. Otherwise: print to stdout.
  - Notes: This command reads YAML only — no backend connections needed.

- [ ] Task 7: Implement `validate env-file` command
  - File: `scripts/env_to_vault.py`
  - Action: Add `cmd_validate(args)` function:
    - Load classification YAML
    - Parse `.env` file via existing `parse_env_file()`
    - Load bootstrap variable names from classification
    - Based on `--backend`:
      - `vault`: allowed keys = bootstrap group only
      - `aws`: allowed keys = bootstrap group minus VAULT_ADDR, VAULT_TOKEN, VAULT_ENV
      - `env`: all keys allowed — just check for unknown variables not in YAML at all
    - Report:
      ```
      Validating .env for backend: vault

      ✓ Bootstrap variables present: 5/7
        Missing: VAULT_ADDR, VAULT_TOKEN

      ⚠ Non-bootstrap variables found (should be in Vault): 34
        - OPENAI_API_KEY (group: llm, type: secret)
        - POSTGRESQL_PASSWORD (group: database, type: secret)
        - PORT (group: app, type: config)
        ...

      ❓ Unknown variables (not in vars-classification.yaml): 2
        - JENKINS_URL
        - OLD_UNUSED_VAR
      ```
  - Notes: Read-only — never modifies `.env`. Exit code: 0 if clean, 1 if issues found (for CI use).

- [ ] Task 8: Implement `remove` command
  - File: `scripts/env_to_vault.py`
  - Action: Add `cmd_remove(args)` function:
    - Load classification YAML
    - Resolve backends for `--env` from `environments` section
    - For each key in `args.keys`:
      - For each backend in environment:
        - Connect via `resolve_backend_client()` (uses `_client_cache`)
        - For Vault backends: read all keys, remove target key from dict, write back (reuse `cmd_vault_delete` logic)
        - For SSM backends: call `ssm_delete_parameter()` per key (reuse `cmd_ssm_delete` logic). Gracefully skip `ParameterNotFound`.
      - Remove variable from `vars-classification.yaml` file:
        - Use `save_classification()` with round-trip preservation (ruamel.yaml)
    - Dry-run by default — display what would happen. `--write` to execute.
    - Output:
      ```
      Remove JENKINS_URL from environment 'dev':

        nas-vault (secret/lenie/dev): exists → will remove
        aws-ssm-main (/lenie/dev/JENKINS_URL): exists → will remove
        vars-classification.yaml (group: app): exists → will remove

      Run with --write to execute.
      ```
    - If a key doesn't exist in a backend: report "not found (skipping)" per backend, continue with others.
    - If a key doesn't exist in YAML: warn but still remove from backends.
  - Notes: Accepts multiple keys (`keys` is nargs="+"). Each key processed independently with individual success/failure reporting. No `--everywhere` flag needed — `remove` always targets all backends for the given environment.

- [ ] Task 9a: Implement `review` command — display logic (read-only)
  - File: `scripts/env_to_vault.py`
  - Action: Add `build_review_data(classification, env, args)` helper function that:
    - Resolves backends for `--env` (with error on unknown env)
    - Reads all data from each backend (uses `_client_cache`)
    - If a backend is unreachable: report warning and mark as "unavailable" (do NOT fail-fast — show data from reachable backends)
    - Builds unified view dict: `{var_name: {backend_name: present_bool, ...}, group: str, type: str}`
    - Detects orphans: keys in backends that are NOT in YAML (union of all backend keys minus all YAML-defined keys)
    - Returns structured review data
  - Action: Add `display_review(review_data, backends)` function that:
    - Prints grouped table (format as shown below)
    - Prints orphan section
    - Prints summary counts: defined, synced, gaps, orphans, unavailable backends
    - Output:
      ```
      Environment 'dev' → backends: nas-vault, aws-ssm-main

      GROUP: database (6 vars)
        ✅ POSTGRESQL_HOST       nas-vault: ✓  aws-ssm-main: ✓  config
        ✅ POSTGRESQL_PASSWORD    nas-vault: ✓  aws-ssm-main: ✓  secret
        ⚠️  POSTGRESQL_SSLMODE    nas-vault: ✗  aws-ssm-main: ✓  config

      GROUP: app (5 vars)
        ✅ PORT                  nas-vault: ✓  aws-ssm-main: ✓  config
        ✅ JENKINS_URL           nas-vault: ✓  aws-ssm-main: ✓  config

      ORPHANS (in backends but NOT in YAML):
        ❓ OLD_API_TOKEN         nas-vault: ✓  aws-ssm-main: ✗

      Summary: 48 defined, 45 synced, 3 gaps, 1 orphan
      ```
  - Notes: Pure display functions — no side effects, easy to test. Depends on Task 3 helpers.

- [ ] Task 9b: Implement `review` command — interactive actions
  - File: `scripts/env_to_vault.py`
  - Action: Add `cmd_review(args)` function that:
    - Calls `build_review_data()` and `display_review()`
    - Presents action menu:
      ```
      Actions:
        [d] Delete variable from all backends + YAML
        [a] Add orphan to YAML
        [q] Quit
      ```
    - Interactive loop:
      - `d` → prompt for variable name → confirm with `[y/N]` → remove from all backends + YAML (reuses `cmd_remove` logic with `--write` implicit)
      - `a` → prompt for orphan variable name → prompt for group (suggest existing groups), type (secret/config), description → add to YAML via `save_classification()`
      - `q` → exit
    - After each action: reload YAML, re-read backends, refresh display
    - **Warning on entry**: "Note: YAML changes made outside this session will be overwritten by save operations."
  - Notes: Depends on Task 9a (display), Task 8 (`cmd_remove` logic), Task 3 (`save_classification`). Interactive prompts use `input("[y/N]: ").strip().lower()` pattern. All destructive actions require per-action confirmation.

- [ ] Task 10: Create unit tests
  - File: `scripts/tests/__init__.py` (new, empty)
  - File: `scripts/tests/test_env_to_vault.py` (new)
  - Action: Create test file with the following test classes (minimum **30 test methods** total):
    - `TestLoadClassification` (~6 tests): YAML loading, derived defaults (secret→SecureString, config→String), `get_backends_for_env()`, `get_all_variables()`, `get_bootstrap_variables()`, **missing file error** (graceful exit), **malformed YAML error** (graceful exit), **unknown env name** (clear error), **unknown backend type** (clear error)
    - `TestCompare` (~5 tests): diff computation with mock data (new/changed/removed/in-sync), `--show-values` output, identical sources, empty source/target, **backend connection failure** (error reported, not crash)
    - `TestGenerateEnvExample` (~4 tests): output for `--backend vault` (only bootstrap), `--backend aws` (bootstrap minus Vault vars), `--backend env` (all variables), `example`/`default` value precedence
    - `TestValidateEnvFile` (~4 tests): detection of excess variables, missing bootstrap vars, unknown variables, clean `.env` passes with exit code 0
    - `TestRemove` (~5 tests): mock vault and ssm clients, removal from both backends, dry-run output, YAML file updated after removal (round-trip preservation verified), key not found in one backend (graceful skip), key not in YAML but in backend (warn and remove)
    - `TestReviewDisplay` (~3 tests): `build_review_data()` output structure, `display_review()` output format, orphan detection, **empty/non-existent backend** shown as empty (not error)
    - `TestReviewInteractive` (~3 tests): mock `input()` for delete action, mock `input()` for add-orphan action, quit action
  - Notes: Use `unittest.mock.patch` for `get_vault_client`, `get_ssm_client`, `vault_read_all`, `ssm_read_all`, `ssm_delete_parameter`. Use `tempfile.NamedTemporaryFile` for YAML file manipulation in tests. Use `patch("builtins.input")` for interactive input mocking. Verify ruamel.yaml round-trip: write YAML with comments, modify via script, verify comments preserved.

### Acceptance Criteria

- [ ] AC 1: Given a `vars-classification.yaml` exists with backend definitions and environment mappings, when running `compare --from nas-vault --to aws-ssm-main --env dev`, then the output shows keys only in source, only in target, with different values, and count of in-sync keys, with all values masked by default.

- [ ] AC 2: Given the same setup, when running `compare --from nas-vault --to aws-ssm-main --env dev --show-values`, then full unmasked values are displayed with a warning header.

- [ ] AC 3: Given a `vars-classification.yaml` exists, when running `compare --from env --to nas-vault --env dev`, then the `.env` file contents are compared against Vault, treating `.env` as a read-only source.

- [ ] AC 4: Given a `vars-classification.yaml` with variable `JENKINS_URL` defined in group `app`, when running `remove JENKINS_URL --env dev` (dry-run), then the output lists all backends in `dev` environment and reports what would be removed (without making changes).

- [ ] AC 5: Given the same setup, when running `remove JENKINS_URL --env dev --write`, then the variable is removed from all backends (nas-vault and aws-ssm-main) AND removed from `vars-classification.yaml` with comments and formatting preserved (ruamel.yaml round-trip).

- [ ] AC 6: Given a `vars-classification.yaml` exists, when running `generate env-example --backend vault`, then the output contains only bootstrap group variables with descriptions as comments, example/default values, and a header indicating the target backend.

- [ ] AC 7: Given the same setup, when running `generate env-example --backend aws`, then the output contains bootstrap variables MINUS Vault-specific ones (VAULT_ADDR, VAULT_TOKEN, VAULT_ENV).

- [ ] AC 8: Given the same setup, when running `generate env-example --backend env`, then the output contains ALL variables from all groups.

- [ ] AC 9: Given a `.env` file with 34 non-bootstrap variables and `SECRETS_BACKEND=vault`, when running `validate env-file --backend vault`, then the output reports missing bootstrap vars, lists non-bootstrap variables that should be in Vault, lists unknown variables not in YAML, and exits with code 1.

- [ ] AC 10: Given a `.env` file with only bootstrap variables, when running `validate env-file --backend vault`, then the output confirms the file is clean and exits with code 0.

- [ ] AC 11: Given backends with data, when running `review --env dev`, then an interactive table is displayed showing all YAML-defined variables with their presence in each backend (✓/✗), plus orphan variables found in backends but not in YAML.

- [ ] AC 12: Given the `review` interactive session, when user selects `[d]` and enters a variable name and confirms, then the variable is removed from all backends and removed from YAML.

- [ ] AC 13: Given the `review` interactive session, when user selects `[a]` and enters an orphan variable name with group and type, then the variable is added to the correct group in `vars-classification.yaml`.

- [ ] AC 14: Given a `vars-classification.yaml` with `environments.dev.backends: [nas-vault, aws-ssm-main]`, when any command resolves backends for `--env dev`, then it correctly connects to both `nas-vault` (Vault KV v2) and `aws-ssm-main` (SSM with profile `default`).

- [ ] AC 15: Given `vars-classification.yaml` defines a variable with `type: secret` and no explicit `ssm_type`, when the script resolves SSM type, then it derives `SecureString`. Given `type: config`, it derives `String`.

- [ ] AC 16: Given unit tests exist in `scripts/tests/test_env_to_vault.py`, when running `cd scripts && PYTHONPATH=. pytest tests/ -v`, then all ≥30 tests pass with mocked Vault/SSM clients (no real backend connections).

- [ ] AC 17: Given `vars-classification.yaml` is complete, when `get_all_variables()` is called, then it returns ≥48 variables covering 100% of `nas.env.example` keys + all undocumented `os.getenv()` calls found in `backend/library/**/*.py`.

- [ ] AC 18: Given `--env staging` is used but `environments.staging` is not defined in YAML, when any command runs, then a clear error message is printed ("Environment 'staging' not defined in vars-classification.yaml. Available: dev, prod, qa") and the script exits with code 1.

- [ ] AC 19: Given a backend `nas-vault` is unreachable (Vault sealed or network error), when running `review --env dev`, then the output shows "nas-vault: ⚠ unavailable" for all variables, displays data from reachable backends, and prints a warning — NOT a crash/traceback.

- [ ] AC 20: Given `vars-classification.yaml` has a YAML syntax error, when any command that loads YAML runs, then a clear error message with line number is printed and the script exits with code 1.

- [ ] AC 21: Given a backend definition has `type: aws_secrets_manager` (unsupported), when the script tries to resolve a client, then a clear error message is printed ("Backend type 'aws_secrets_manager' is not supported. Supported types: vault_kv2, aws_ssm") and the script exits with code 1.

## Additional Context

### Dependencies

- **ruamel.yaml** — required for reading and round-trip writing `vars-classification.yaml`. Add `ruamel.yaml>=0.18` to `pyproject.toml` `[dependencies]`. Use lazy import via `_require_ruamel()` in script (same pattern as hvac/boto3). Chosen over pyyaml for comment and formatting preservation.
- **Existing backends** — no changes to Vault KV v2 or SSM API usage patterns.
- **No new external services** — all operations use existing Vault and SSM connections.

### Testing Strategy

- **Framework**: `unittest.TestCase` + `pytest` (matches project conventions)
- **Location**: `scripts/tests/test_env_to_vault.py`
- **Isolation**: `patch.dict(os.environ, {...}, clear=True)` for all tests
- **Mocking**: `hvac` and `boto3` mocked via `unittest.mock.patch` / `sys.modules`; `yaml` available directly
- **Coverage targets**:
  - YAML loading and parsing (`load_classification()`, derived defaults logic)
  - `compare` diff computation (new/changed/removed/in-sync)
  - `generate env-example` output for each backend type
  - `validate env-file` detection of excess variables
  - `remove` dispatch to correct backends per environment config
  - `review` display logic (without interactive input — mock `input()`)
  - Error handling: unknown env, backend connection failure, malformed YAML, unknown backend type
- **Run command**: `cd scripts && PYTHONPATH=. pytest tests/ -v`

### Notes

**Data sources for YAML population:**
- `infra/docker/nas.env.example` — most complete template (38 vars)
- `os.getenv()` calls in `backend/library/**/*.py` — 14 undocumented variables found
- `.env_example` (root) — 31 vars, outdated but useful for cross-reference
- `backend/server.py` cfg.require() calls — 15 validated variables with defaults

**AWS accounts:**
- `008971653395` (profile `default`) = active production account
- `049706517731` (profile `lenie-ai-2025-admin`) = target migration account

**Backend naming convention:** `{location}-{type}`, lowercase + hyphens (e.g., `nas-vault`, `aws-ssm-main`, `aws-ssm-2025`).

**High-risk items:**
- ~~YAML comment preservation~~: **RESOLVED** — using `ruamel.yaml` with `typ='rt'` for round-trip preservation. Comments and formatting are maintained across read-modify-write cycles.
- Vault read-modify-write race: `remove` for Vault reads all keys, removes target, writes back. If another process writes between read and write, those changes are lost. Low risk for a single-user CLI tool, but worth noting.
- ~~Top-level `delete` vs nested `vault delete`~~: **RESOLVED** — renamed to `remove` to avoid UX confusion. `remove` = all backends; `vault delete`/`ssm delete` = single backend.
- Concurrent YAML edits during `review`: if user edits `vars-classification.yaml` in an editor while `review` session is active, those changes will be overwritten on save. Mitigated by warning on entry: "YAML changes made outside this session will be overwritten."

**Future considerations (out of scope):**
- `config_loader.py` reading `_BOOTSTRAP_VARS` from YAML (confirmed direction)
- K8s manifest generation from YAML classification
- CI pipeline validation step using `validate env-file`
- Auto-discovery command that scans codebase for `os.getenv()` / `cfg.require()` calls and updates YAML
