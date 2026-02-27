# NAS Deployment — QNAP TS-453Be

Full Lenie stack running on a local QNAP NAS for personal use and testing.

> **Related docs:** [Docker_Local.md](Docker_Local.md) — local Docker Compose development, [frontend-deployment.md](../frontend-deployment.md) — AWS frontend deployment.

## Hardware

| Parameter | Value |
|-----------|-------|
| Model | QNAP TS-453Be |
| CPU | Intel Celeron J3455 (x86_64) |
| RAM | 16 GB |
| OS | QTS (Linux 5.10) |
| Docker | Container Station (Docker 27.x) |

## Stack Overview

| Service | Container | Image | Port | Description |
|---------|-----------|-------|------|-------------|
| Frontend React | `lenie-ai-frontend` | `192.168.200.7:5005/lenie-ai-frontend` | 3000 | Main web interface |
| Admin Panel | `lenie-ai-app2` | `192.168.200.7:5005/lenie-ai-app2` | 3001 | Admin panel (app2) |
| Backend | `lenie-ai-server` | `192.168.200.7:5005/lenie-ai-server` | 5055 | Flask API server |
| PostgreSQL | `lenie-ai-db` | `192.168.200.7:5005/lenie-ai-db` | 5434 | PostgreSQL 17 + pgvector (upgrade to 18 pending — B-69) |
| Vault | `lenie-vault` | `hashicorp/vault:latest` | 8210 | HashiCorp Vault secrets manager |
| **Registry** | `lenie-registry` | `registry:2` | 5005 | Private Docker registry (infra) |

All application services are orchestrated via `docker compose` using `compose.nas.yaml`.
The registry container runs standalone (started once, persists across deployments).

**Network topology:** All services are connected via Docker network `lenie-net`. Backend connects to DB by container name `lenie-ai-db` on internal port 5432. Frontend containers serve static files via nginx — API calls go from the user's browser directly to the backend port.

## Access URLs

From any device on the local network:

- **Frontend:** http://192.168.200.7:3000
- **Admin Panel:** http://192.168.200.7:3001
- **Backend API:** http://192.168.200.7:5055
- **Vault UI:** http://192.168.200.7:8210/ui
- **Registry catalog:** http://192.168.200.7:5005/v2/_catalog

## Prerequisites

### SSH Access

SSH key-based authentication must be configured for `admin@192.168.200.7`:

```bash
# From WSL (sshpass required):
sshpass -p '<NAS_PASSWORD>' ssh-copy-id -i /mnt/c/Users/<USER>/.ssh/id_rsa.pub -o StrictHostKeyChecking=no admin@192.168.200.7

# Verify:
ssh admin@192.168.200.7 "echo OK"
```

### Docker Path on QNAP

Docker binary is not in the default PATH on QNAP. Full path:

```
/share/CACHEDEV1_DATA/.qpkg/container-station/usr/bin/.libs/docker
```

Container Station must be installed via QNAP App Center.

### Port Conflicts

QNAP uses several ports by default. Known conflicts:

| Port | Used by | Solution |
|------|---------|----------|
| 5000-5001 | Apache WebDAV | Backend uses 5055, registry uses 5005 |
| 5050 | Python process | — |
| 5433 | Local PostgreSQL | DB container uses 5434 |
| 8200 | UPnP Media Server | Vault uses 8210 |

## Private Docker Registry

A private Docker registry (`registry:2`) runs on the NAS to store built images. This replaces the previous workflow of exporting images to `.tar.gz`, transferring via `scp`, and loading with `docker load`.

### One-Time Setup

#### 1. Start registry container on NAS

```bash
ssh admin@192.168.200.7
DOCKER=/share/CACHEDEV1_DATA/.qpkg/container-station/usr/bin/.libs/docker

$DOCKER run -d --name lenie-registry \
  --restart unless-stopped \
  -p 5005:5000 \
  -v lenie-registry-data:/var/lib/registry \
  registry:2
```

#### 2. Configure insecure-registries

The registry runs without TLS (HTTP only), so both the PC and NAS must allow it as an insecure registry.

**PC (Docker Desktop):**

Settings → Docker Engine → add to JSON:

```json
{
  "insecure-registries": ["192.168.200.7:5005"]
}
```

Apply & Restart Docker Desktop.

**NAS (Container Station):**

Edit `/share/CACHEDEV1_DATA/.qpkg/container-station/etc/docker.json`, add:

```json
{
  "insecure-registries": ["192.168.200.7:5005"]
}
```

Restart Container Station from QNAP App Center (or reboot NAS).

#### 3. Verify

```bash
# From PC — push a test image
docker pull hello-world
docker tag hello-world 192.168.200.7:5005/hello-world
docker push 192.168.200.7:5005/hello-world

# Check registry catalog
curl http://192.168.200.7:5005/v2/_catalog
# Expected: {"repositories":["hello-world"]}

# From NAS — pull it back
ssh admin@192.168.200.7
DOCKER=/share/CACHEDEV1_DATA/.qpkg/container-station/usr/bin/.libs/docker
$DOCKER pull 192.168.200.7:5005/hello-world
```

### Garbage Collection

Over time, the registry accumulates old image layers. To reclaim disk space:

```bash
ssh admin@192.168.200.7
DOCKER=/share/CACHEDEV1_DATA/.qpkg/container-station/usr/bin/.libs/docker

# Run garbage collection (removes unreferenced blobs)
$DOCKER exec lenie-registry bin/registry garbage-collect /etc/docker/registry/config.yml

# Check registry disk usage
$DOCKER exec lenie-registry du -sh /var/lib/registry
```

## Deployment

### Automated Deploy Script

The script `infra/docker/nas-deploy.sh` handles building images, pushing to the private registry, and deploying via `docker compose`.

```bash
# Deploy all services (build → push → compose up)
./infra/docker/nas-deploy.sh

# Deploy specific service(s)
./infra/docker/nas-deploy.sh frontend
./infra/docker/nas-deploy.sh backend app2

# Push existing image without rebuilding
./infra/docker/nas-deploy.sh --skip-build backend

# Only run compose up on NAS (no build/push)
./infra/docker/nas-deploy.sh --compose-only

# Copy compose.nas.yaml to NAS and deploy
./infra/docker/nas-deploy.sh --sync-compose

# Sync compose file and deploy specific services
./infra/docker/nas-deploy.sh --sync-compose frontend app2
```

The script performs these steps for each service:

1. Build Docker image locally (faster than on NAS CPU)
2. Tag image for the private registry (`192.168.200.7:5005/...`)
3. Push to registry via `docker push`
4. On NAS: `docker compose pull` to fetch updated images
5. On NAS: `docker compose up -d` to recreate changed containers

### Compose File

The compose file lives at `/share/Container/lenie-compose/compose.nas.yaml` on the NAS. Source of truth is `infra/docker/compose.nas.yaml` in the repo.

To sync it to NAS:

```bash
./infra/docker/nas-deploy.sh --sync-compose
# or manually:
scp infra/docker/compose.nas.yaml admin@192.168.200.7:/share/Container/lenie-compose/compose.nas.yaml
```

### Docker Compose Commands on NAS

```bash
ssh admin@192.168.200.7
DOCKER=/share/CACHEDEV1_DATA/.qpkg/container-station/usr/bin/.libs/docker

# Status
$DOCKER compose -f /share/Container/lenie-compose/compose.nas.yaml ps

# Restart all
$DOCKER compose -f /share/Container/lenie-compose/compose.nas.yaml restart

# Restart single service
$DOCKER compose -f /share/Container/lenie-compose/compose.nas.yaml restart lenie-ai-server

# View logs
$DOCKER compose -f /share/Container/lenie-compose/compose.nas.yaml logs --tail 50 lenie-ai-server

# Stop everything
$DOCKER compose -f /share/Container/lenie-compose/compose.nas.yaml down

# Pull latest images and recreate
$DOCKER compose -f /share/Container/lenie-compose/compose.nas.yaml pull
$DOCKER compose -f /share/Container/lenie-compose/compose.nas.yaml up -d
```

### Migration from Old Workflow

If migrating from the previous tar.gz/scp deployment:

1. Configure insecure-registries on PC and NAS (see [Private Docker Registry](#private-docker-registry))
2. Start the registry container on NAS
3. Verify push/pull with a test image
4. Sync compose file: `./nas-deploy.sh --sync-compose`
5. Create external volumes (if they don't exist):
   ```bash
   ssh admin@192.168.200.7
   DOCKER=/share/CACHEDEV1_DATA/.qpkg/container-station/usr/bin/.libs/docker
   $DOCKER volume create lenie-ai-db-data
   $DOCKER volume create lenie-ai-data
   ```
6. Stop old containers:
   ```bash
   $DOCKER stop lenie-ai-frontend lenie-ai-app2 lenie-ai-server lenie-ai-db
   $DOCKER rm lenie-ai-frontend lenie-ai-app2 lenie-ai-server lenie-ai-db
   ```
7. Push all images and deploy: `./nas-deploy.sh`

### Manual Deploy (Step by Step)

If the script is not available or you need to deploy manually:

#### 1. Build image locally

```bash
# Frontend
docker build -t lenie-ai-frontend:latest -f web_interface_react/Dockerfile .

# Admin Panel
docker build -t lenie-ai-app2:latest -f web_interface_app2/Dockerfile .

# Backend
docker build -t lenie-ai-server:latest -f backend/Dockerfile .

# Database
docker build -t lenie-ai-db:latest -f infra/docker/Postgresql/Dockerfile .
```

All builds use the project root as Docker context (required for `shared/` directory access).

#### 2. Tag and push to registry

```bash
docker tag lenie-ai-frontend:latest 192.168.200.7:5005/lenie-ai-frontend:latest
docker push 192.168.200.7:5005/lenie-ai-frontend:latest

# Repeat for each image...
```

#### 3. Deploy on NAS

```bash
ssh admin@192.168.200.7
DOCKER=/share/CACHEDEV1_DATA/.qpkg/container-station/usr/bin/.libs/docker
$DOCKER compose -f /share/Container/lenie-compose/compose.nas.yaml pull
$DOCKER compose -f /share/Container/lenie-compose/compose.nas.yaml up -d
```

## Database Setup

The database container uses a custom image built from `infra/docker/Postgresql/Dockerfile`:
- Base: `postgres:17-bookworm`
- Extension: `postgresql-17-pgvector`
- Init scripts from `backend/database/init/` (auto-executed on first run):
  - `01-create-database.sql` — creates `lenie-ai` database
  - `02-create-extension.sql` — installs pgvector extension
  - `03-create-table.sql` — creates `web_documents` table with indexes
  - `04-create-table.sql` — creates `websites_embeddings` table with vector index

Data is persisted in Docker volume `lenie-ai-db-data` (external, survives compose down).

### Connecting from local machine

```bash
psql -h 192.168.200.7 -p 5434 -U postgres -d lenie-ai
```

## Backend Configuration

The backend reads environment variables from `/share/Container/lenie-env/.env` on the NAS. Create this file from `infra/docker/nas.env.example` template and fill in your secrets:

Key differences from local `.env`:

| Variable | Local | NAS |
|----------|-------|-----|
| `POSTGRESQL_HOST` | `localhost` or `192.168.200.7` | `lenie-ai-db` (Docker network) |
| `POSTGRESQL_PORT` | `5434` (external) | `5432` (internal) |
| `POSTGRESQL_DATABASE` | `lenie` | `lenie-ai` |

To update the env file on the NAS:

```bash
# First time: cp infra/docker/nas.env.example infra/docker/nas.env && edit nas.env with real secrets
scp infra/docker/nas.env admin@192.168.200.7:/share/Container/lenie-env/.env
# Then restart the backend container
```

## Vault

HashiCorp Vault runs on the NAS for secrets management. Auto-unseal is configured via AWS KMS — Vault unseals itself automatically after every NAS restart.

> **Detailed setup:** [Vault_Setup.md](Vault_Setup.md) — full installation, auto-unseal migration, token management.

### Configuration

Config file location on NAS: `/share/Container/vault/config/vault.hcl`

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
  kms_key_id = "<KMS_KEY_ID>"
}

ui = true
disable_mlock = true
api_addr = "http://0.0.0.0:8200"
```

AWS credentials for KMS are provided via env file at `/share/Container/lenie-env/vault.env` (see `infra/docker/vault.env.example` for template). The KMS key and IAM user are managed by CloudFormation stack `lenie-nas-vault-kms-unseal` on the personal AWS account (profile `ziutus-Administrator`).

Persistent data directories on NAS:
- `/share/Container/vault/config` — configuration
- `/share/Container/vault/data` — encrypted storage
- `/share/Container/vault/logs` — logs

### Initial Setup (First Time Only)

```bash
# Initialize (generates unseal key and root token)
$DOCKER exec -e VAULT_ADDR=http://127.0.0.1:8200 lenie-vault \
  vault operator init -key-shares=1 -key-threshold=1 -format=json

# Save the unseal_keys_b64[0] and root_token from the output!

# Unseal
$DOCKER exec -e VAULT_ADDR=http://127.0.0.1:8200 lenie-vault \
  vault operator unseal <UNSEAL_KEY>

# Enable KV v2 secrets engine
$DOCKER exec -e VAULT_ADDR=http://127.0.0.1:8200 -e VAULT_TOKEN=<ROOT_TOKEN> lenie-vault \
  vault secrets enable -path=lenie kv-v2
```

### After NAS Restart

With auto-unseal configured, **Vault unseals itself automatically** — no manual intervention needed.

If auto-unseal is not yet configured (or AWS KMS is unreachable), unseal manually:

```bash
ssh admin@192.168.200.7
DOCKER=/share/CACHEDEV1_DATA/.qpkg/container-station/usr/bin/.libs/docker
$DOCKER exec -e VAULT_ADDR=http://127.0.0.1:8200 lenie-vault \
  vault operator unseal <UNSEAL_KEY>
```

### Connecting Backend to Vault

Set these variables in the backend `.env`:

```bash
VAULT_URL=http://192.168.200.7:8210/
VAULT_TOKEN=<ROOT_TOKEN>
```

Or when backend runs on the same Docker network as Vault, use the container name.

## Frontend Configuration

Both frontends are SPAs served by nginx. The API backend URL is configured in the browser:

- **Frontend React** (`/connect` page): Select "Docker" mode and set URL to `http://192.168.200.7:5055`
- **Admin Panel** (login page): Backend URL is set during login

This setting is saved in the browser's localStorage.

## Troubleshooting

### Check container status

```bash
ssh admin@192.168.200.7
DOCKER=/share/CACHEDEV1_DATA/.qpkg/container-station/usr/bin/.libs/docker

# Via compose
$DOCKER compose -f /share/Container/lenie-compose/compose.nas.yaml ps

# All lenie containers (including registry)
$DOCKER ps --filter name=lenie
```

### View logs

```bash
$DOCKER compose -f /share/Container/lenie-compose/compose.nas.yaml logs --tail 50 lenie-ai-server
$DOCKER compose -f /share/Container/lenie-compose/compose.nas.yaml logs --tail 50 lenie-ai-db
$DOCKER logs --tail 50 lenie-vault
$DOCKER logs --tail 50 lenie-registry
```

### Container keeps restarting

Check logs for errors. Common issues:
- **`ModuleNotFoundError`** in backend — Dockerfile ENTRYPOINT must use venv Python (`/app/.venv/bin/python`)
- **Port already in use** — check with `netstat -tlnp | grep <PORT>`
- **Database connection refused** — ensure DB container is running and healthy (`docker compose ps`)

### Rebuild and redeploy a single service

```bash
./infra/docker/nas-deploy.sh backend
```

### Disk space on NAS

```bash
ssh admin@192.168.200.7 'df -h /share/CACHEDEV1_DATA'
```

Clean unused Docker images on NAS:

```bash
$DOCKER system prune -a
```

### Registry troubleshooting

```bash
# Check registry is running
$DOCKER ps --filter name=lenie-registry

# List all images in registry
curl http://192.168.200.7:5005/v2/_catalog

# List tags for a specific image
curl http://192.168.200.7:5005/v2/lenie-ai-server/tags/list

# Check registry logs
$DOCKER logs --tail 50 lenie-registry
```
