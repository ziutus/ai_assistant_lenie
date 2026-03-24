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

Configuration (`vault.hcl`) — includes KMS auto-unseal (see [Auto-Unseal with AWS KMS](#auto-unseal-with-aws-kms)):

```hcl
storage "file" {
  path = "/vault/file"
}

listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = 1
}

seal "awskms" {
  region     = "eu-central-1"
  kms_key_id = "0c6a400d-096b-4b9c-9098-7a0ec7a74f15"
}

ui = true
disable_mlock = true
api_addr = "http://0.0.0.0:8200"
```

### 3. Start the container

Vault is managed via `compose.nas.yaml`. Sync the compose file and start:

```bash
./infra/docker/nas-deploy.sh --sync-compose
ssh admin@192.168.200.7
DOCKER=/share/CACHEDEV1_DATA/.qpkg/container-station/usr/bin/.libs/docker
$DOCKER compose -f /share/Container/lenie-compose/compose.nas.yaml up -d lenie-vault
```

See [NAS_Deployment.md](NAS_Deployment.md) for full compose workflow.

### 4. Initialize (one-time)

```bash
docker exec -it vault sh -c \
  "VAULT_ADDR=http://127.0.0.1:8200 vault operator init -key-shares=1 -key-threshold=1"
```

**Save the Unseal Key and Root Token!** They are required for unsealing after restarts and for admin operations.

### 5. Unseal (manual — replaced by auto-unseal, see below)

Required after every container restart (only if auto-unseal is not configured):

```bash
docker exec -it vault sh -c \
  "VAULT_ADDR=http://127.0.0.1:8200 vault operator unseal <UNSEAL_KEY>"
```

For automatic unsealing, see [Auto-Unseal with AWS KMS](#auto-unseal-with-aws-kms).

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

## Auto-Unseal with AWS KMS

Instead of manually unsealing Vault after every NAS restart, Vault can automatically unseal itself using an AWS KMS key. This eliminates the need to store or enter the unseal key manually.

> **Status:** Auto-unseal is **active** since 2026-03-03. Migration from Shamir to KMS completed and tested — Vault auto-unseals after container restart.

### How it works

1. NAS restarts → Vault container starts (sealed)
2. Vault detects `seal "awskms"` in config → calls AWS KMS to decrypt the master key
3. Vault unseals itself automatically — no manual intervention needed

### Prerequisites

AWS infrastructure is managed by CloudFormation stack `lenie-nas-vault-kms-unseal` on the personal AWS account (profile `ziutus-Administrator`), region `eu-central-1`. The stack creates:

| Resource | Description |
|----------|-------------|
| KMS Key | `alias/lenie-vault-unseal` — symmetric key with auto-rotation |
| IAM User | `lenie-vault-nas-unseal` — programmatic access only |
| IAM Policy | `kms:Encrypt`, `kms:Decrypt`, `kms:DescribeKey` — scoped to the single key |

Deploy (one-time):

```bash
cd infra/aws/cloudformation
aws cloudformation create-stack \
  --stack-name lenie-nas-vault-kms-unseal \
  --template-body file://templates/vault-kms-unseal.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --region eu-central-1 \
  --profile ziutus-Administrator
```

After deployment, retrieve `AccessKeyId`, `SecretAccessKey`, and `KmsKeyId` from stack outputs:

```bash
aws cloudformation describe-stacks \
  --stack-name lenie-nas-vault-kms-unseal \
  --region eu-central-1 \
  --profile ziutus-Administrator \
  --query 'Stacks[0].Outputs' --output table
```

### Configuration

#### 1. Update `vault.hcl` on NAS

Add the `seal "awskms"` block to `/share/vault/config/vault.hcl`:

```hcl
storage "file" {
  path = "/vault/file"
}

listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = 1
}

seal "awskms" {
  region     = "eu-central-1"
  kms_key_id = "<KMS_KEY_ID_FROM_STACK_OUTPUT>"
}

ui = true
disable_mlock = true
api_addr = "http://0.0.0.0:8200"
```

#### 2. Create `vault.env` on NAS

Create the env file from the template and fill in real credentials:

```bash
# Copy template
cp infra/docker/vault.env.example infra/docker/vault.env
# Edit with real values from CloudFormation outputs
# Then copy to NAS:
scp infra/docker/vault.env admin@192.168.200.7:/share/Container/lenie-env/vault.env
```

The file should contain:

```bash
AWS_ACCESS_KEY_ID=<AccessKeyId from stack output>
AWS_SECRET_ACCESS_KEY=<SecretAccessKey from stack output>
AWS_REGION=eu-central-1
```

#### 3. Update compose file

The `compose.nas.yaml` already references this env file. Sync it to NAS:

```bash
./infra/docker/nas-deploy.sh --sync-compose
```

### Migration from Shamir to KMS (one-time)

> **Completed 2026-03-03.** Steps below are kept for reference.

If Vault was previously initialized with Shamir keys (manual unseal), you must migrate to KMS unseal:

```bash
ssh admin@192.168.200.7
DOCKER=/share/CACHEDEV1_DATA/.qpkg/container-station/usr/bin/.libs/docker

# 1. Update vault.hcl with the seal "awskms" block (see above)
# 2. Ensure vault.env is in place at /share/Container/lenie-env/vault.env

# 3. Recreate the container (IMPORTANT: must use --force-recreate, not "docker restart",
#    because "docker restart" does NOT reload env_file — credentials won't be available)
$DOCKER compose -f /share/Container/lenie-compose/compose.nas.yaml up -d --force-recreate lenie-vault

# 4. Wait for Vault to start in migration mode (~10s)
sleep 12

# 5. Perform the migration (requires the OLD Shamir unseal key)
$DOCKER exec -e VAULT_ADDR=http://127.0.0.1:8200 lenie-vault \
  vault operator unseal -migrate <CURRENT_SHAMIR_UNSEAL_KEY>

# 6. Verify — Seal Type should now be "awskms", Sealed: false
$DOCKER exec -e VAULT_ADDR=http://127.0.0.1:8200 lenie-vault \
  vault status
```

**Important:** Always use `docker compose up -d --force-recreate` (not `docker restart`) when changing `vault.env` or `vault.hcl`. `docker restart` reuses the existing container environment and will not pick up changes to `env_file`.

After migration, Vault will auto-unseal on every restart. The old Shamir unseal key is no longer needed for daily operations (but keep it stored safely as a recovery key).

### Troubleshooting

**Vault fails to auto-unseal (stays sealed after restart):**

```bash
# Check Vault logs for KMS errors
$DOCKER logs --tail 50 lenie-vault

# Common causes:
# - AWS credentials expired or invalid → check vault.env
# - KMS key disabled or deleted → check AWS Console
# - No internet from NAS → check NAS network/DNS
# - Wrong region in vault.hcl → must be eu-central-1
```

**Test KMS connectivity from Vault container:**

```bash
# Install AWS CLI in the container (temporary debug)
$DOCKER exec -e VAULT_ADDR=http://127.0.0.1:8200 lenie-vault \
  vault status
# Look for "Seal Type: awskms" and "Sealed: false"
```

### Cost

- KMS key: ~$1/month (fixed, regardless of usage)
- KMS API calls: negligible (only on Vault startup)
