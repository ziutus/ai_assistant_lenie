# unified-config-loader

Pluggable configuration loader for Python applications with support for multiple backends.

## Backends

- **env** (default) — loads from `.env` file + environment variables via `python-dotenv`
- **vault** — loads from HashiCorp Vault KV v2 (requires `hvac`)
- **aws** — loads from AWS SSM Parameter Store (requires `boto3`)

## Usage

```python
from unified_config_loader import load_config

cfg = load_config()
db_host = cfg.require("POSTGRESQL_HOST")
debug = cfg.require("DEBUG", "false")
```

The backend is selected via `SECRETS_BACKEND` environment variable (default: `env`).

## Installation

```bash
# Base (env backend only)
pip install unified-config-loader

# With Vault support
pip install unified-config-loader[vault]

# With AWS SSM support
pip install unified-config-loader[aws]

# All backends
pip install unified-config-loader[vault,aws]
```

## Bootstrap Variables

These variables are always read from the real environment, regardless of backend:

- `SECRETS_BACKEND` — backend to use: `env`, `vault`, `aws`
- `SECRETS_ENV` — environment name (`dev`, `prod`, `qa`), default: `dev`
- `PROJECT_CODE` — project code for secret paths, default: `lenie`
- `VAULT_ADDR`, `VAULT_TOKEN` — required for vault backend
- `AWS_REGION` — required for aws backend, default: `eu-central-1`

## API

- `load_config() -> Config` — create or return cached Config singleton
- `get_config() -> Config` — alias for load_config()
- `reset_config()` — clear cache and undo os.environ injection (for tests)
- `Config.require(key, default=None) -> str` — get value or exit if missing

## Running Tests

```bash
cd shared_python/unified-config-loader
PYTHONPATH=. uvx pytest tests/ -v
```
