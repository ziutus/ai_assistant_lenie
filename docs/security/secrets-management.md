# Secrets Management

This document describes how Project Lenie handles configuration and secrets across different deployment environments.

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Env Backend Setup (Local Development)](#env-backend-setup-local-development)
- [Vault Setup (Docker / NAS)](#vault-setup-docker--nas)
- [AWS SSM Parameter Store Setup](#aws-ssm-parameter-store-setup)
- [Variable Classification](#variable-classification)
- [Adding New Variables](#adding-new-variables)
- [Troubleshooting](#troubleshooting)
- [env_to_vault.py Tooling Reference](#envtovaultpy-tooling-reference)

## Architecture Overview

The configuration system is built around the **config_loader** module (`backend/library/config_loader.py`) which provides a unified `Config` object that replaces scattered `os.getenv()` calls.

### Three Backends

| Backend | `SECRETS_BACKEND` value | Use case | Source |
|---------|------------------------|----------|--------|
| **env** | `env` (default) | Local development | `.env` file + real environment |
| **vault** | `vault` | Docker / NAS deployments | HashiCorp Vault KV v2 |
| **aws** | `aws` | Lambda / cloud deployments | AWS SSM Parameter Store |

### Bootstrap vs Application Variables

Variables are split into two categories:

- **Bootstrap variables** — always read from the real environment (`.env` file or shell). These configure _which_ backend to use and _how_ to connect to it. They are never uploaded to secret backends.
- **Application variables** — database credentials, API keys, LLM settings, etc. When using `vault` or `aws` backend, these are loaded from the remote secret store at startup.

Bootstrap variables: `SECRETS_BACKEND`, `SECRETS_ENV`, `PROJECT_CODE`, `VAULT_ADDR`, `VAULT_TOKEN`, `ENV_DATA`, `AWS_REGION`. Additionally, `VAULT_ENV` is recognized as a deprecated fallback for `SECRETS_ENV` (use `SECRETS_ENV` for new deployments).

### Config Loader Flow

```
1. Application starts (server.py / Lambda handler)
2. load_config() reads SECRETS_BACKEND from real environment
3. Factory creates the appropriate backend (EnvBackend / VaultBackend / AWSSSMBackend)
4. Backend loads all configuration key-value pairs
5. Config object (dict subclass) is returned as a singleton
6. For non-env backends: loaded values are injected into os.environ
   for backward compatibility with library modules still using os.getenv()
```

Usage in application code:

```python
from library.config_loader import get_config

cfg = get_config()
db_host = cfg.require("POSTGRESQL_HOST")          # exits if missing
debug   = cfg.require("DEBUG", "false")            # uses default if missing
optional = cfg.get("SOME_OPTIONAL_VAR")            # returns None if missing
```

## Env Backend Setup (Local Development)

The `env` backend is the default. It reads all variables from a `.env` file in the project root (loaded via `python-dotenv`) and the real shell environment.

To generate a complete `.env` file with all application variables:

```bash
python scripts/env_to_vault.py generate env-example --backend env --output .env
```

Then fill in the actual values (database credentials, API keys, etc.). The `.env` file is git-ignored and must never be committed.

## Vault Setup (Docker / NAS)

### Prerequisites

- HashiCorp Vault server accessible from the application
- KV v2 secrets engine enabled at `secret/` mount point
- Authentication token with read access to the secret path

### Configuration

Set these bootstrap variables in `.env`:

```env
SECRETS_BACKEND="vault"
SECRETS_ENV="dev"
VAULT_ADDR="http://vault.local:8200"
VAULT_TOKEN="<your-vault-token>"
```

### Secret Path Convention

Secrets are stored as a single KV v2 secret at:

```
secret/{PROJECT_CODE}/{SECRETS_ENV}
```

For example, with defaults: `secret/lenie/dev`

All application variables are stored as key-value pairs within this single secret. This means one `vault kv put` command (or the `env_to_vault.py` upload tool) writes all variables at once.

### Auto-Unseal via AWS KMS

The NAS Vault instance uses AWS KMS for auto-unseal (eu-central-1 region). This means Vault automatically unseals on restart without manual intervention. The KMS key is managed in a separate AWS account.

### Uploading Secrets to Vault

```bash
# Dry-run (preview what would be uploaded)
python scripts/env_to_vault.py vault upload --env dev

# Write all variables from .env to Vault
python scripts/env_to_vault.py vault upload --env dev --write

# Set a single key
python scripts/env_to_vault.py vault set --env dev OPENAI_API_KEY=<your-openai-api-key>

# List all keys in Vault
python scripts/env_to_vault.py vault list --env dev
```

## AWS SSM Parameter Store Setup

### Prerequisites

- AWS credentials with `ssm:GetParametersByPath`, `ssm:PutParameter`, `ssm:DeleteParameter` permissions
- Parameters stored as `SecureString` type (encrypted at rest with AWS-managed KMS key)

### Configuration

Set these bootstrap variables in `.env`:

```env
SECRETS_BACKEND="aws"
SECRETS_ENV="dev"
AWS_REGION="us-east-1"
```

AWS credentials are resolved via the standard boto3 credential chain (environment variables, AWS profile, instance role, etc.).

### SSM Path Convention

Each variable is stored as a separate SSM parameter at:

```
/{PROJECT_CODE}/{SECRETS_ENV}/{KEY}
```

For example: `/lenie/dev/POSTGRESQL_HOST`, `/lenie/dev/OPENAI_API_KEY`

### Lambda VPC Constraint

Lambda functions running inside a VPC (e.g., `sqs-to-rds`) cannot reach SSM Parameter Store without a NAT Gateway or VPC endpoint. To avoid additional costs, these Lambdas continue to receive configuration via CloudFormation environment variables rather than the SSM backend. This is an intentional trade-off documented in the Lambda handler code.

### Uploading Secrets to SSM

```bash
# Dry-run (preview what would be uploaded)
python scripts/env_to_vault.py ssm upload --env dev

# Write all variables from .env to SSM
python scripts/env_to_vault.py ssm upload --env dev --write

# Set a single key
python scripts/env_to_vault.py ssm set --env dev OPENAI_API_KEY=<your-openai-api-key>

# List all keys in SSM
python scripts/env_to_vault.py ssm list --env dev
```

### Sync Between Backends

```bash
# Sync from Vault to SSM (dry-run)
python scripts/env_to_vault.py sync --env dev --from vault --to ssm

# Sync from Vault to SSM (write)
python scripts/env_to_vault.py sync --env dev --from vault --to ssm --write
```

## Variable Classification

All configuration variables are defined in [`scripts/vars-classification.yaml`](../scripts/vars-classification.yaml) — the Single Source of Truth (SSOT) for variable metadata.

### Variable Types

| Type | Description | SSM Parameter Type | K8s Resource |
|------|-------------|-------------------|--------------|
| `secret` | Sensitive values (API keys, passwords, tokens) | `SecureString` | `Secret` |
| `config` | Non-sensitive settings (hostnames, ports, flags) | `String` | `ConfigMap` |

### Variable Groups

The YAML file organizes variables into functional groups:

| Group | Description | Example Variables |
|-------|-------------|-------------------|
| `bootstrap` | Backend selection and connection | `SECRETS_BACKEND`, `VAULT_ADDR`, `SECRETS_ENV` |
| `database` | PostgreSQL connection | `POSTGRESQL_HOST`, `POSTGRESQL_PASSWORD` |
| `llm` | LLM provider settings | `LLM_PROVIDER`, `OPENAI_API_KEY`, `EMBEDDING_MODEL` |
| `aws` | AWS credentials and resources | `AWS_ACCESS_KEY_ID`, `AWS_S3_WEBSITE_CONTENT` |
| `app` | Application runtime | `PORT`, `DEBUG`, `STALKER_API_KEY` |
| `integrations` | Third-party services | `ASSEMBLYAI`, `FIRECRAWL_API_KEY`, `LANGFUSE_HOST` |
| `media` | Media processing | `TRANSCRIPT_PROVIDER`, `YOUTUBE_DEFAULT_LANGUAGE` |
| `gcp` | Google Cloud Platform | `GCP_PROJECT_ID`, `GCP_LOCATION` |
| `legacy` | Deprecated variables | `AWS_FREE_TIER_*`, `WEBSITES_CACHE_DIR` |

## Adding New Variables

1. **Define the variable** in `scripts/vars-classification.yaml` under the appropriate group. Specify `description`, `type` (`secret` or `config`), `required` (or `required_when`), `example`, and `used_by` fields.

2. **Upload to backends** using the env_to_vault.py tool:
   ```bash
   # Set in Vault (writes immediately, no --write needed)
   python scripts/env_to_vault.py vault set --env dev NEW_VAR=value

   # Set in SSM (writes immediately, no --write needed)
   python scripts/env_to_vault.py ssm set --env dev NEW_VAR=value
   ```

3. **Verify with compare** to ensure consistency:
   ```bash
   python scripts/env_to_vault.py compare --from env --to nas-vault --env dev
   ```

4. **Update code** to use the variable via `cfg.require("NEW_VAR")` or `cfg.get("NEW_VAR")`.

## Troubleshooting

### Missing VAULT_TOKEN

```
ERROR: VAULT_TOKEN must be set when using vault backend
```

Ensure `.env` contains `VAULT_TOKEN` with a valid Vault authentication token. Check that the token has not expired.

### Vault Authentication Failed

```
ERROR: Vault authentication failed at http://vault.local:8200 — check VAULT_TOKEN
```

The token exists but Vault rejected it. Possible causes:
- Token has been revoked or expired
- Vault server was resealed (check auto-unseal status)
- Wrong Vault instance (check `VAULT_ADDR`)

### SSM Path Not Found

```
WARNING: AWS SSM: no parameters found under /lenie/dev/
```

No parameters exist at the expected path. Either:
- Parameters have not been uploaded yet (run `ssm upload --env dev --write`)
- `SECRETS_ENV` or `PROJECT_CODE` do not match the SSM path prefix
- AWS credentials lack `ssm:GetParametersByPath` permission

### Backend Unreachable

```
ERROR: Failed to load config from Vault at http://vault.local:8200: ConnectionError(...)
```

The Vault or SSM endpoint is not reachable. Check:
- Network connectivity (VPN if accessing NAS Vault remotely)
- Vault server is running and unsealed
- For SSM: AWS region matches where parameters are stored

### Unknown SECRETS_BACKEND Value

```
ERROR: Unknown SECRETS_BACKEND value: 'xyz'. Valid options: aws, env, vault
```

`SECRETS_BACKEND` must be one of: `env`, `vault`, `aws`.

## env_to_vault.py Tooling Reference

The `scripts/env_to_vault.py` script provides CLI commands for managing secrets across backends.

### Per-Backend Commands

| Command | Description |
|---------|-------------|
| `vault upload --env dev` | Upload all .env variables to Vault (dry-run without `--write`) |
| `vault set --env dev KEY=value` | Set a single key in Vault |
| `vault delete --env dev KEY` | Delete a key from Vault |
| `vault list --env dev` | List all keys in Vault |
| `vault get --env dev KEY` | Get a single value from Vault |
| `ssm upload --env dev` | Upload all .env variables to SSM (dry-run without `--write`) |
| `ssm set --env dev KEY=value` | Set a single key in SSM |
| `ssm delete --env dev KEY` | Delete a key from SSM |
| `ssm list --env dev` | List all keys in SSM |
| `ssm get --env dev KEY` | Get a single value from SSM |

### Sync Command

| Command | Description |
|---------|-------------|
| `sync --env dev --from vault --to ssm` | Sync variables from Vault to SSM (dry-run without `--write`) |

### YAML-Driven Commands

These commands use `scripts/vars-classification.yaml` as the source of truth:

| Command | Description |
|---------|-------------|
| `compare --from env --to nas-vault --env dev` | Compare variables between two sources |
| `compare --from nas-vault --to aws-ssm-main --env dev --show-values` | Compare with value display |
| `review --env dev` | Review all backends for an environment |
| `remove OLD_VAR --env dev` | Remove a variable from all backends (dry-run without `--write`) |
| `generate env-example --backend vault` | Generate `.env` template for vault backend (bootstrap vars only) |
| `generate env-example --backend env --output .env_example` | Generate full `.env` template for env backend |
| `validate env-file --backend vault` | Validate `.env` has correct variables for the backend |
