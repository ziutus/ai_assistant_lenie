# NAS Deployment — QNAP TS-453Be

Full Lenie stack running on a local QNAP NAS for personal use and testing.

> **Related docs:** [Docker_Local.md](Docker_Local.md) — local Docker Compose development, [frontend-deployment.md](frontend-deployment.md) — AWS frontend deployment.

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
| Frontend React | `lenie-ai-frontend` | `lenie-ai-frontend:latest` | 3000 | Main web interface |
| Admin Panel | `lenie-ai-app2` | `lenie-ai-app2:latest` | 3001 | Admin panel (app2) |
| Backend | `lenie-ai-server` | `lenie-ai-server:latest` | 5055 | Flask API server |
| PostgreSQL | `lenie-ai-db` | `lenie-ai-db:latest` | 5434 | PostgreSQL 17 + pgvector |
| Vault | `lenie-vault` | `hashicorp/vault:latest` | 8210 | HashiCorp Vault secrets manager |

All services use `--restart unless-stopped` policy.

**Network topology:** Backend and database are connected via Docker network `lenie-net` (backend connects to DB by container name `lenie-ai-db` on internal port 5432). Frontend containers serve static files via nginx and don't need the Docker network — API calls go from the user's browser directly to the backend port.

## Access URLs

From any device on the local network:

- **Frontend:** http://192.168.200.7:3000
- **Admin Panel:** http://192.168.200.7:3001
- **Backend API:** http://192.168.200.7:5055
- **Vault UI:** http://192.168.200.7:8210/ui

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
| 5000-5001 | Apache WebDAV | Backend uses 5055 |
| 5050 | Python process | — |
| 5433 | Local PostgreSQL | DB container uses 5434 |
| 8200 | UPnP Media Server | Vault uses 8210 |

## Deployment

### Automated Deploy Script

The script `infra/docker/nas-deploy.sh` handles building, transferring, and deploying images to the NAS.

```bash
# Deploy all services
./infra/docker/nas-deploy.sh

# Deploy specific service(s)
./infra/docker/nas-deploy.sh frontend
./infra/docker/nas-deploy.sh backend app2
./infra/docker/nas-deploy.sh db

# Transfer and restart without rebuilding
./infra/docker/nas-deploy.sh --skip-build backend
```

The script performs these steps for each service:
1. Build Docker image locally (faster than on NAS CPU)
2. Export image to `.tar.gz`
3. Transfer via `scp` to NAS
4. Load image on NAS with `docker load`
5. Stop and remove old container
6. Start new container with correct ports, volumes, and network
7. Clean up temporary archive files

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

#### 2. Export and transfer

```bash
docker save <IMAGE>:latest | gzip > /tmp/<IMAGE>.tar.gz
scp /tmp/<IMAGE>.tar.gz admin@192.168.200.7:/share/Container/
```

#### 3. Load on NAS

```bash
ssh admin@192.168.200.7
DOCKER=/share/CACHEDEV1_DATA/.qpkg/container-station/usr/bin/.libs/docker
$DOCKER load -i /share/Container/<IMAGE>.tar.gz
```

#### 4. Start containers

```bash
DOCKER=/share/CACHEDEV1_DATA/.qpkg/container-station/usr/bin/.libs/docker

# Database (start first)
$DOCKER run -d --name lenie-ai-db \
  --restart unless-stopped \
  -p 5434:5432 \
  -e POSTGRES_PASSWORD=postgres \
  -v lenie-ai-db-data:/var/lib/postgresql/data \
  lenie-ai-db:latest

# Create network and connect DB
$DOCKER network create lenie-net
$DOCKER network connect lenie-net lenie-ai-db

# Backend
$DOCKER run -d --name lenie-ai-server \
  --restart unless-stopped \
  --network lenie-net \
  -p 5055:5000 \
  --env-file /share/Container/lenie-env/.env \
  -v lenie-ai-data:/app/data \
  lenie-ai-server:latest

# Frontend
$DOCKER run -d --name lenie-ai-frontend \
  --restart unless-stopped \
  -p 3000:80 \
  lenie-ai-frontend:latest

# Admin Panel
$DOCKER run -d --name lenie-ai-app2 \
  --restart unless-stopped \
  -p 3001:80 \
  lenie-ai-app2:latest
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

Data is persisted in Docker volume `lenie-ai-db-data`.

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

HashiCorp Vault runs on the NAS for secrets management.

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

ui = true
disable_mlock = true
api_addr = "http://0.0.0.0:8200"
```

Persistent data directories on NAS:
- `/share/Container/vault/config` — configuration
- `/share/Container/vault/data` — encrypted storage
- `/share/Container/vault/logs` — logs

### Container

```bash
$DOCKER run -d --name lenie-vault \
  --restart unless-stopped \
  --cap-add IPC_LOCK \
  -p 8210:8200 \
  -v /share/Container/vault/config:/vault/config \
  -v /share/Container/vault/data:/vault/file \
  -v /share/Container/vault/logs:/vault/logs \
  hashicorp/vault:latest server
```

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

Vault seals itself on restart. You must unseal it manually:

```bash
ssh admin@192.168.200.7
DOCKER=/share/CACHEDEV1_DATA/.qpkg/container-station/usr/bin/.libs/docker
$DOCKER exec -e VAULT_ADDR=http://127.0.0.1:8200 lenie-vault \
  vault operator unseal <UNSEAL_KEY>
```

Alternatively, access Vault UI at http://192.168.200.7:8210/ui and enter the unseal key.

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
$DOCKER ps --filter name=lenie-ai
$DOCKER ps --filter name=lenie-vault
```

### View logs

```bash
$DOCKER logs --tail 50 lenie-ai-server
$DOCKER logs --tail 50 lenie-ai-db
$DOCKER logs --tail 50 lenie-vault
```

### Container keeps restarting

Check logs for errors. Common issues:
- **`ModuleNotFoundError`** in backend — Dockerfile ENTRYPOINT must use venv Python (`/app/.venv/bin/python`)
- **Port already in use** — check with `netstat -tlnp | grep <PORT>`
- **Database connection refused** — ensure DB container is running and connected to `lenie-net` network

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
