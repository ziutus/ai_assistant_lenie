## Epic 20: Secrets Management — Migrate .env to Vault & AWS SSM

Developer has all application secrets and configuration loaded from environment-appropriate secret managers (HashiCorp Vault for Docker/NAS, AWS SSM Parameter Store + Secrets Manager for AWS) — `.env` files contain only minimal bootstrap variables.

**Stories:** 20-1, 20-2, 20-3, 20-4, 20-5, 20-6

Implementation notes:
- Story 20-1 must be completed first (defines the interface)
- Stories 20-2 and 20-3 can be done in parallel (independent backends)
- Story 20-4 depends on 20-1 (and ideally 20-2/20-3 for testing)
- Story 20-5 is the final cleanup step
- Story 20-6 extends env_to_vault.py with compare/review/remove + YAML SSOT (discovered scope gap after 20-3/20-4)

### Story 20.1: Create Unified Config Loader Module

As a **developer**,
I want a config loader module in `backend/library/` that provides a unified interface for retrieving configuration from different secret backends,
so that the rest of the codebase does not need to know whether secrets come from Vault, AWS SSM, or environment variables.

**Acceptance Criteria:**

**Given** the backend needs to load configuration at startup
**When** the developer creates `backend/library/config_loader.py`
**Then** the module provides a `load_config()` function that returns a dictionary of all configuration values
**And** the backend type is selected via `SECRETS_BACKEND` env var (`vault`, `aws`, or `env` for backward compatibility)

**Given** the config loader is initialized with `SECRETS_BACKEND=env`
**When** the backend starts
**Then** all configuration is read from environment variables (current behavior) — this is the fallback/migration path

**Given** the config loader encounters an unreachable secret backend
**When** the backend starts
**Then** a clear error message is logged identifying which backend failed and why
**And** the process exits with a non-zero exit code

**Technical notes:**
- Module location: `backend/library/config_loader.py`
- Bootstrap env vars (always read from `.env`/environment): `SECRETS_BACKEND`, `VAULT_ADDR`, `VAULT_TOKEN`, `AWS_REGION`, `ENV_DATA`
- Return type: `dict[str, str]` matching current `os.environ` key names
- Backend interface: abstract base or simple protocol with `load()` method
- `env` backend wraps current `os.environ` / `python-dotenv` behavior for zero-disruption migration

**FRs:** FR33, FR34
**Status:** pending

### Story 20.2: Implement HashiCorp Vault Backend (Docker/NAS)

As a **developer**,
I want the config loader to support HashiCorp Vault as a secret backend,
so that the Docker/NAS deployment reads all configuration from Vault instead of `.env` files.

**Acceptance Criteria:**

**Given** `SECRETS_BACKEND=vault` and `VAULT_ADDR` points to the NAS Vault instance
**When** the backend starts
**Then** all application configuration is loaded from Vault (database credentials, API keys, LLM config, service tokens)
**And** the values are available to the application via the same key names as current env vars

**Given** the developer organizes secrets in Vault
**When** secrets are stored
**Then** they are organized under a path like `secret/lenie/<ENV_DATA>/` (e.g., `secret/lenie/dev/POSTGRESQL_HOST`)

**Given** the Vault instance is unreachable
**When** the backend starts with `SECRETS_BACKEND=vault`
**Then** the error message includes the Vault address and connection error details

**Technical notes:**
- Use `hvac` Python library (HashiCorp Vault client)
- Add `hvac` as optional dependency: `uv add --optional vault hvac`
- Auth method: token-based (`VAULT_TOKEN` from bootstrap env) — simplest for single-user NAS
- KV v2 secrets engine (standard for Vault)
- Vault path convention: `secret/data/lenie/{ENV_DATA}/<key>`
- Test with NAS Vault before marking done

**FRs:** FR35
**Status:** pending

### Story 20.3: Implement AWS SSM / Secrets Manager Backend

As a **developer**,
I want the config loader to support AWS SSM Parameter Store and Secrets Manager as secret backends,
so that the AWS deployment (Lambda + EC2) reads all configuration from AWS-native services.

**Acceptance Criteria:**

**Given** `SECRETS_BACKEND=aws` and proper AWS credentials are available
**When** the backend starts (Lambda or EC2)
**Then** all application configuration is loaded from SSM Parameter Store (non-secret config) and Secrets Manager (credentials, API keys)

**Given** the developer organizes parameters in AWS
**When** parameters are stored
**Then** non-secret config is in SSM Parameter Store under `/<ProjectCode>/<ENV_DATA>/config/<key>` (e.g., `/lenie/dev/config/LLM_PROVIDER`)
**And** secrets are in Secrets Manager under `/<ProjectCode>/<ENV_DATA>/secret/<key>` (e.g., `/lenie/dev/secret/OPENAI_API_KEY`)

**Given** Lambda functions need to access SSM/Secrets Manager
**When** the function starts
**Then** IAM roles already permit SSM and Secrets Manager access (verify existing policies, add if missing)

**Technical notes:**
- Use `boto3` (already a Lambda dependency)
- SSM `GetParametersByPath` for bulk loading non-secret config
- Secrets Manager `GetSecretValue` for individual secrets (or batch with `BatchGetSecretValue`)
- Consider caching for Lambda cold starts (load once, reuse across invocations)
- Secrets classification: `POSTGRESQL_PASSWORD`, `OPENAI_API_KEY`, `STALKER_API_KEY`, AssemblyAI/Firecrawl tokens → Secrets Manager; everything else → SSM Parameter Store
- CloudFormation: may need to add IAM policy for Secrets Manager access to Lambda execution roles

**FRs:** FR36
**Status:** pending

### Story 20.4: Integrate Config Loader into Server and Lambda Handlers

As a **developer**,
I want `server.py` and Lambda handlers to use the config loader module instead of reading directly from environment variables,
so that all configuration flows through the unified secret management layer.

**Acceptance Criteria:**

**Given** `server.py` currently reads config via `os.environ` and `python-dotenv`
**When** the developer integrates the config loader
**Then** `server.py` calls `load_config()` at startup and uses the returned values
**And** all `os.environ.get()` / `os.getenv()` calls for application config are replaced with config loader access

**Given** Lambda handlers currently read config from Lambda environment variables
**When** the developer integrates the config loader
**Then** handlers call `load_config()` (with `SECRETS_BACKEND=aws`) and use the returned values
**And** Lambda environment variables for secrets are removed from CloudFormation templates (replaced by runtime SSM/Secrets Manager reads)

**Given** the config loader is integrated
**When** the backend starts in Docker with `SECRETS_BACKEND=vault`
**Then** the application starts and serves requests successfully using Vault-sourced config

**Given** the config loader is integrated
**When** a Lambda function starts with `SECRETS_BACKEND=aws`
**Then** the function processes requests successfully using SSM/Secrets Manager-sourced config

**Technical notes:**
- `server.py`: replace `load_dotenv()` + `os.environ` pattern with `config = load_config()`
- Lambda handlers: add config loader call in handler initialization (outside handler function for reuse)
- Identify all `os.environ.get()` / `os.getenv()` call sites in `server.py` and `library/` modules
- Keep `SECRETS_BACKEND=env` as default for zero-disruption transition
- CloudFormation Lambda templates: remove secret env vars from `Environment.Variables`, add `SECRETS_BACKEND=aws` + `ENV_DATA`

**FRs:** FR37, FR38
**Status:** pending

### Story 20.5: Update .env_example and Document Config Flow

As a **developer**,
I want `.env_example` to reflect the new bootstrap-only structure and clear documentation of the secrets management flow,
so that future developers understand how configuration works in each environment.

**Acceptance Criteria:**

**Given** `.env_example` currently lists all configuration variables
**When** the developer updates it
**Then** it contains only bootstrap variables: `SECRETS_BACKEND`, `VAULT_ADDR`, `VAULT_TOKEN`, `AWS_REGION`, `ENV_DATA`
**And** each variable has a comment explaining its purpose and which backends use it
**And** a header comment explains the three backends (`env`, `vault`, `aws`) and points to documentation

**Given** the developer documents the new config flow
**When** documentation is written
**Then** `docs/secrets-management.md` is created covering: architecture overview, Vault setup (Docker/NAS), AWS SSM/Secrets Manager setup, variable classification (secret vs config), adding new variables, troubleshooting

**Given** the migration is complete
**When** the developer verifies the setup
**Then** Docker Compose `compose.yaml` no longer passes secrets via `env_file` (only bootstrap vars)
**And** `.env` file in project root contains only bootstrap variables

**Technical notes:**
- Update `infra/docker/compose.yaml` env_file or environment section
- Create `docs/secrets-management.md`
- Update `CLAUDE.md` Environment Variables section to reference new flow
- Keep old `.env_example` content as comment block or separate `env_example_legacy.md` for reference during migration

**FRs:** FR39
**Status:** pending

### Story 20.6: Extend env_to_vault.py with Compare, Review, and Variable Classification SSOT

As a **developer**,
I want `env_to_vault.py` extended with tools to compare backend state, review variable coverage, and manage the full variable lifecycle via a YAML Single Source of Truth,
so that after migrating secrets (Stories 20-2/20-3) I can verify consistency, clean up orphans, and maintain configuration across environments.

**Origin:** Discovered during Stories 20-3/20-4 — after migrating to Vault and SSM, there were no tools to compare state between backends, clean up unused keys, or manage the variable lifecycle. Configuration documentation was fragmented across 16+ files with ~14 variables undocumented.

**Tech Spec:** `_bmad-output/implementation-artifacts/tech-spec-env-to-vault-compare-review-classify.md` (ready-for-dev, 10 tasks, 21 ACs)

**Scope:**
1. Create `scripts/vars-classification.yaml` — SSOT for ~50 config variables with classification (secret/config), backend definitions, and environment mappings
2. Add YAML loader infrastructure to `env_to_vault.py` (ruamel.yaml for round-trip preservation)
3. Implement `compare` command — universal comparison between any two sources (vault/ssm/env-file)
4. Implement `review` command — interactive review of YAML vs backend state, with actions (add orphans, delete variables)
5. Implement `remove` command — remove variable from all backends in an environment + YAML
6. Implement `generate env-example` command — produce `.env_example` from YAML for a given backend type
7. Implement `validate env-file` command — check that `.env` contains only appropriate variables
8. Unit tests (≥30 test methods)

**Acceptance Criteria:** 21 criteria defined in tech spec (ACs 1–21).

**Subsumes:** B-66 (unit tests for env_to_vault.py — covered by Task 10 in tech spec)
**Partially addresses:** Story 20-5 (`generate env-example` replaces manual .env_example update)

**Technical notes:**
- ruamel.yaml required (round-trip YAML preservation for comments/formatting)
- Named backend instances (nas-vault, aws-ssm-main, aws-ssm-2025)
- Dry-run by default, `--write` to execute (existing pattern)
- Client connection caching for multi-backend commands

**FRs:** FR35, FR36 (operational tooling)
**Status:** pending
