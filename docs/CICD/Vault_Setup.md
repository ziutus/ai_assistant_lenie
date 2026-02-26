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
VAULT_ENV=dev                          # optional, defaults to "dev"
SECRETS_BACKEND=vault                  # set to "vault" to use Vault instead of .env
```

| Variable | Description | Required |
|----------|-------------|----------|
| `VAULT_ADDR` | Vault server URL (NAS port 8210) | Yes |
| `VAULT_TOKEN` | Authentication token | Yes |
| `VAULT_ENV` | Environment name for secret path (`dev`, `prod`, `qa`). Default: `dev` | No |
| `SECRETS_BACKEND` | Set to `vault` to activate Vault backend in `config_loader.py` | Yes |

## Managing Secrets (`scripts/env_to_vault.py`)

Python script for managing secrets in Vault. Requires `hvac` package. Reads `VAULT_ADDR` and `VAULT_TOKEN` from `.env`.

### Full migration from .env

```bash
# Dry-run (shows what would be uploaded, no changes)
python scripts/env_to_vault.py upload --env dev

# Actually write all variables to Vault
python scripts/env_to_vault.py upload --env dev --write

# Upload from a different .env file to a different environment
python scripts/env_to_vault.py upload --env prod --env-file .env.prod --write
```

Bootstrap variables (`VAULT_ADDR`, `VAULT_TOKEN`, `SECRETS_BACKEND`) are automatically excluded from the upload.

### Add or update keys (patch)

```bash
# Set a single key (other keys are untouched)
python scripts/env_to_vault.py set --env dev NEW_KEY=new_value

# Set multiple keys at once
python scripts/env_to_vault.py set --env dev KEY1=value1 KEY2=value2
```

### Delete keys

```bash
# Delete a single key
python scripts/env_to_vault.py delete --env dev OLD_KEY

# Delete multiple keys
python scripts/env_to_vault.py delete --env dev KEY1 KEY2
```

### List and read keys

```bash
# List all keys (values are masked)
python scripts/env_to_vault.py list --env dev

# Get the actual value of a key
python scripts/env_to_vault.py get --env dev OPENAI_API_KEY
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
