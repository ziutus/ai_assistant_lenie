# HashiCorp Vault Setup

Vault stores application secrets for Project Lenie. Runs on the NAS as a Docker container with persistent file storage.

> **Related docs:** [NAS_Deployment.md](NAS_Deployment.md) — full NAS stack, [../development-guide.md](../development-guide.md) — dev setup.

## Architecture

```
secret/lenie/dev     -- development environment secrets (54 keys)
secret/lenie/prod    -- production (future)
secret/lenie/qa      -- QA (future)
```

All configuration keys for a given environment are stored as a single KV v2 secret. The backend reads them via `config_loader.py` using the `hvac` library.

## NAS Installation (Docker)

### 1. Create directories

```bash
mkdir -p /share/vault/data /share/vault/config
```

### 2. Copy configuration file

From the developer machine:

```bash
scp docs/CICD/vault.hcl admin@192.168.200.7:/share/vault/config/vault.hcl
```

Configuration (`vault.hcl`):

```hcl
storage "file" {
  path = "/vault/file"
}

listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = 1
}

ui = true
api_addr = "http://0.0.0.0:8200"
```

### 3. Start the container

```bash
docker run -d \
  --name vault \
  --restart=unless-stopped \
  --cap-add=IPC_LOCK \
  -p 8210:8200 \
  -v /share/vault/data:/vault/file \
  -v /share/vault/config:/vault/config \
  hashicorp/vault:1.21.3 vault server -config=/vault/config/vault.hcl
```

### 4. Initialize (one-time)

```bash
docker exec -it vault sh -c \
  "VAULT_ADDR=http://127.0.0.1:8200 vault operator init -key-shares=1 -key-threshold=1"
```

**Save the Unseal Key and Root Token!** They are required for unsealing after restarts and for admin operations.

### 5. Unseal

Required after every container restart:

```bash
docker exec -it vault sh -c \
  "VAULT_ADDR=http://127.0.0.1:8200 vault operator unseal <UNSEAL_KEY>"
```

### 6. Enable KV v2 engine

```bash
docker exec -it vault sh -c \
  "VAULT_ADDR=http://127.0.0.1:8200 VAULT_TOKEN=<ROOT_TOKEN> vault secrets enable -path=secret kv-v2"
```

### 7. Create a working token

```bash
docker exec -it vault sh -c \
  "VAULT_ADDR=http://127.0.0.1:8200 VAULT_TOKEN=<ROOT_TOKEN> vault token create -ttl=8760h -policy=root"
```

Use the generated token as `VAULT_TOKEN` in `.env`.

## Environment Variables

Add to your `.env` file:

```bash
VAULT_ADDR=http://192.168.200.7:8210
VAULT_TOKEN=hvs.xxxxxxxxxxxxx
SECRETS_ENV=dev                        # optional, defaults to "dev"
SECRETS_BACKEND=vault                  # set to "vault" to use Vault instead of .env
```

| Variable | Description | Required |
|----------|-------------|----------|
| `VAULT_ADDR` | Vault server URL (NAS port 8210) | Yes |
| `VAULT_TOKEN` | Authentication token | Yes |
| `SECRETS_ENV` | Environment name for secret path (`dev`, `prod`, `qa`). Default: `dev`. Falls back to `VAULT_ENV` for backward compat. | No |
| `SECRETS_BACKEND` | Set to `vault` to activate Vault backend in `config_loader.py` | Yes |

## Managing Secrets (`scripts/env_to_vault.py`)

Unified script for managing secrets in both Vault and AWS SSM Parameter Store. Supports full migration, individual key operations, and synchronization between backends.

Requirements: `hvac` (for Vault), `boto3` (for SSM).

Bootstrap variables (`VAULT_ADDR`, `VAULT_TOKEN`, `SECRETS_BACKEND`) are automatically excluded from uploads.

### Vault commands

```bash
# Full migration from .env
python scripts/env_to_vault.py vault upload --env dev                  # dry-run
python scripts/env_to_vault.py vault upload --env dev --write          # write all

# Single key operations
python scripts/env_to_vault.py vault set --env dev KEY=value           # add/update (patch)
python scripts/env_to_vault.py vault set --env dev K1=v1 K2=v2        # multiple keys
python scripts/env_to_vault.py vault delete --env dev KEY              # delete key
python scripts/env_to_vault.py vault list --env dev                    # list all (masked)
python scripts/env_to_vault.py vault get --env dev OPENAI_API_KEY      # get actual value
```

### AWS SSM Parameter Store commands

All parameters stored as `SecureString` under `/lenie/{env}/`. Uses default boto3 credential chain.

```bash
# Full migration from .env
python scripts/env_to_vault.py ssm upload --env dev                    # dry-run
python scripts/env_to_vault.py ssm upload --env dev --write            # write all

# Single key operations
python scripts/env_to_vault.py ssm set --env dev KEY=value             # add/update
python scripts/env_to_vault.py ssm delete --env dev KEY                # delete
python scripts/env_to_vault.py ssm list --env dev                      # list all (masked)
python scripts/env_to_vault.py ssm get --env dev OPENAI_API_KEY        # get actual value

# Optional AWS flags (for all ssm commands)
python scripts/env_to_vault.py ssm list --env dev --region eu-central-1
python scripts/env_to_vault.py ssm list --env dev --profile lenie-ai-2025-admin
```

### Sync between backends

Compares source and target, shows diff, writes only new/changed keys. Does **not** delete keys that exist only in the target.

```bash
# Vault -> SSM
python scripts/env_to_vault.py sync --env dev --from vault --to ssm            # dry-run
python scripts/env_to_vault.py sync --env dev --from vault --to ssm --write    # actually sync

# SSM -> Vault
python scripts/env_to_vault.py sync --env dev --from ssm --to vault --write
```

## Web UI

Vault UI is available at: http://192.168.200.7:8210/ui/vault/auth

Log in with a valid token to browse and manage secrets via the web interface.

## Token Management

Tokens expire. The working token created in step 7 has a TTL of 8760 hours (1 year).

**Check token status:**

```bash
curl -s -H "X-Vault-Token: $VAULT_TOKEN" $VAULT_ADDR/v1/auth/token/lookup-self | python -m json.tool
```

**Create a new token** (requires root token):

```bash
docker exec -it vault sh -c \
  "VAULT_ADDR=http://127.0.0.1:8200 VAULT_TOKEN=<ROOT_TOKEN> vault token create -ttl=8760h -policy=root"
```

**If root token is lost** and you have the unseal key:

```bash
# Start root token generation
docker exec -it vault sh -c "VAULT_ADDR=http://127.0.0.1:8200 vault operator generate-root -init"

# Provide unseal key
docker exec -it vault sh -c "VAULT_ADDR=http://127.0.0.1:8200 vault operator generate-root"

# Decode the encoded token
docker exec -it vault sh -c \
  "VAULT_ADDR=http://127.0.0.1:8200 vault operator generate-root -decode=<ENCODED_TOKEN> -otp=<OTP>"
```
