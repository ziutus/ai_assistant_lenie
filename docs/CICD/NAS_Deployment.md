# NAS Deployment — QNAP TS-453Be

Full Lenie stack running on a local QNAP NAS for personal use and testing.

> **Security scope:** This runbook describes the local setup, including intentional
> development shortcuts; it is not a production security baseline. See the
> [local security profile](../security/local-development-security.md) for their
> conditions and the [production readiness checklist](../security/production-readiness.md)
> before exposing the stack to a corporate network or deploying it to cloud.

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
| Scheduler worker | `lenie-worker` | `192.168.200.7:5005/lenie-ai-server` | — | `worker.py --scheduler` + job types (`feed_check`, `feed_auto_import`, `feed_daily`, `content_group_suggest`, `entity_enrichment`, `obsidian_reimport`, `tool_candidate_detect`, …) |
| Document worker | `lenie-document-worker` | `192.168.200.7:5005/lenie-ai-document-worker` | — | `worker.py --types document_prepare` (przygotowanie dokumentów, osobny obraz) |
| Legacy AWS bridge | `lenie-cloud-bridge` | `192.168.200.7:5005/lenie-ai-server` | — | `worker.py --types legacy_aws_pull` — pobieranie bufora DynamoDB z ery serverless |
| Migrations (one-shot) | `lenie-migrate` | `192.168.200.7:5005/lenie-ai-server` | — | `alembic upgrade heads` przy starcie stacka (`restart: "no"`) |
| PostgreSQL | `lenie-ai-db` | `192.168.200.7:5005/lenie-ai-db` | 5434 | PostgreSQL 18 + pgvector |
| MinIO | `lenie-minio` | `192.168.200.7:5005/minio/minio` (pinned digest) | 9000, 9001 | S3-compatible storage (API + web console) |
| MinIO init (one-shot) | `lenie-minio-init` | `192.168.200.7:5005/minio/mc` (pinned digest) | — | Inicjalizacja bucketa (`restart: "no"`) |
| Vault | `lenie-vault` | `192.168.200.7:5005/hashicorp/vault:1.21.3` | 8210 | HashiCorp Vault secrets manager |
| NER service | `lenie-ner-service` | `192.168.200.7:5005/lenie-ner-service` | — | spaCy Polish NER (internal-only, `http://lenie-ner-service:8090`) |
| Obsidian sync | `obsidian-headless-sync` | `192.168.200.7:5005/obsidian-headless-sync:0.0.14` | — | Sync vaulta Obsidian (Epic 42 reimport) |
| Registry UI | `lenie-registry-ui` | `joxit/docker-registry-ui:latest` | 8550 | Web UI for Docker registry |
| **Registry** | `lenie-registry` | `registry:2` | 5005 | Private Docker registry (infra) |

Slack Bot (`lenie-ai-slack-bot`) został usunięty 2026-07-22 wraz z serwerem MCP i nie jest już częścią stacka.

All application services are orchestrated via `docker compose` using `compose.nas.yaml`.
Registry and registry UI are included in the NAS compose file; their existing containers and persistent registry volume are retained across application deployments.

**Network topology:** All services are connected via Docker network `lenie-net`. Backend connects to DB by container name `lenie-ai-db` on internal port 5432. Frontend containers serve static files via nginx — API calls go from the user's browser directly to the backend port.

## Access URLs

From any device on the local network:

- **Frontend:** http://192.168.200.7:3000
- **Admin Panel:** http://192.168.200.7:3001
- **Backend API:** http://192.168.200.7:5055
- **MinIO Console:** http://192.168.200.7:9001
- **Vault UI:** http://192.168.200.7:8210/ui
- **Registry UI:** http://192.168.200.7:8550
- **Registry catalog:** http://192.168.200.7:5005/v2/_catalog

## Prerequisites

### SSH Access

SSH key-based authentication must be configured for `admin@192.168.200.7`. Windows ships a native OpenSSH client (`ssh`/`scp`) — no WSL needed:

```powershell
# One-time key setup from PowerShell (equivalent of ssh-copy-id):
Get-Content $env:USERPROFILE\.ssh\id_rsa.pub | ssh admin@192.168.200.7 "cat >> ~/.ssh/authorized_keys"

# Verify:
ssh admin@192.168.200.7 "echo OK"
```

### Docker Path on QNAP

Docker binary is not in the default PATH on QNAP. Full path:

```
/share/CACHEDEV2_DATA/.qpkg/container-station/bin/docker
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
| 9000, 9001 | — (free) | MinIO S3 API + web console |

## Private Docker Registry

### Pool2 storage and image recovery (2026-09-19)

Container Station now lives on Pool2. Its Docker root is
`/share/CACHEDEV2_DATA/Container/container-station-data/lib/docker`.
`/share/Container` (a QTS-managed share, recreated by the system at every boot)
resolves to `/share/CACHEDEV2_DATA/Container`. Compose bind mounts, the deploy
scripts and the NAS crontab must use `/share/Container/...` — **not** the former
hand-made `/share/ContainerNew` link. That link is not recreated after a reboot,
and when it is missing Docker silently creates an empty directory in its place
(Vault then fails with "A storage backend must be specified"). See the
[NAS incident runbook](../deployment/nas/nas-incident-runbook.md).

There are three image copies with different recovery roles:

| Location | Purpose | Survives registry volume replacement? |
|---|---|---|
| Docker Desktop / Images (PC) | Build and off-NAS image copy | Yes |
| `lenie-registry`, volume `lenie-registry-data` | Distribution to Docker clients | No |
| Container Station / Images (NAS Docker image store) | Local container startup and republishing images | Yes |

The last two share the same storage pool. Neither protects against losing the
whole pool or removing Container Station's Docker root. Image copies also do
not contain PostgreSQL, MinIO, Vault or Obsidian volume data.

Before rebuilding the registry, retain `registry:2`, its UI image and every
application image in Container Station Images. Do not prune these images.
With the exact compose image references already present, containers can be
started using `docker compose ... up -d --pull never`. After restoring the
registry container, use `docker tag` and `docker push` on the NAS to republish
the retained images. Keep the registry's own bootstrap image outside its
registry as well, to avoid a circular recovery dependency.

Additional external image copies in the NAS registry:

| Upstream image | NAS registry reference (prefix `192.168.200.7:5005/`) |
|---|---|
| `hashicorp/vault:1.21.3` | `hashicorp/vault:1.21.3` |
| `ghcr.io/belphemur/obsidian-headless-sync-docker:0.0.14` | `obsidian-headless-sync:0.0.14` |
| `registry:2` | `bootstrap/registry:2` |
| `joxit/docker-registry-ui:latest` (snapshot from 2026-09-19) | `bootstrap/registry-ui:20260919` |

Registry and its UI retain their original compose references for bootstrap;
the other services use the NAS mirror. To replenish an external mirror, pull
the chosen upstream version on Docker Desktop, tag it with the NAS reference,
push it, then pull that reference on the NAS. Verify the resulting image IDs
and retain both copies. For MinIO, use the pinned source digests below.

### MinIO mirror after Docker Hub access failure

On 2026-09-19 Docker Hub denied the pinned MinIO image. The exact upstream
digests were still available from Quay. Their `linux/amd64` variants were
pulled into Docker Desktop and pushed into the NAS registry:

| Image | Quay source digest | NAS registry digest |
|---|---|---|
| `minio/minio:RELEASE.2025-09-07T16-13-09Z` | `14cea493d9a34af32f524e538b8346cf79f3321eff8e708c1e2960462bd8936e` | `52dfd5c0bbd38d3219f2058c7af216d9f9a27a994b7b5baad09bbd38866015ff` |
| `minio/mc:RELEASE.2025-08-13T08-35-41Z` | `a7fe349ef4bd8521fb8497f55c6042871b2ae640607cf99d9bede5e9bdf11727` | `bdfae21c72b19fae5a005c56dddba25a873d75fac3dda60f55aea7e417382cbe` |

Digests in the table omit the `sha256:` prefix. Upstream multi-platform and
republished single-platform manifest digests differ; image config IDs were
checked for equality between Docker Desktop and the NAS registry. Compose
pins the NAS digests. Do not replace them with `latest` during recovery.

### Restore order after replacing Container Station storage

1. Verify the backup and resolved destination paths. Restore configuration,
   create `lenie-net` and the seven external volumes declared in compose.
2. Bootstrap registry and its UI; publish images, then pull them into the NAS
   Docker image store. Keep a copy of the previous compose before replacing it.
3. Restore MinIO's backup into its **empty, stopped** volume before starting
   MinIO. Extract the backup into a separate staging directory **without
   `--strip-components`** and inspect the complete archive layout. The September
   backup has active `.minio.sys/` and `lenie-storage/` at its root, alongside
   an older nested `_data/` tree; the first archive entries alone are misleading.
   Restore the complete archive root into the stopped volume. Stripping two
   path components flattened bucket contents into the volume root; a healthy
   MinIO process alone did not detect the incorrect layout.
   Verify an actual object read after restoring, not just the health endpoint.
4. Start PostgreSQL, preserve its freshly initialized database under a separate
   name, then restore the custom-format dump with `pg_restore --exit-on-error
   --create -U postgres -d postgres`. Do not overwrite an existing live database.
5. Start Vault from its restored bind mounts and verify `initialized=true` and
   `sealed=false`. Run `lenie-migrate` successfully before starting the backend
   and workers. Check document/contact counts and storage access.
6. Restore the host-health collector script as well as its cron entry. An
   existing cron entry pointing to a missing script leaves workers deferred.
7. Verify Obsidian sync configuration and volume contents before any reimport.
   Follow the [batch backfill procedure](../deployment/nas/obsidian-batch-backfill.md);
   do not start a full one-shot `obsidian_reimport` as a migration step.

Recovery validation on 2026-09-19: the PostgreSQL dump restored 10,527 documents,
600 contacts and 9,191 embeddings. MinIO's corrected archive layout exposed
1,441 objects (233,992,698 bytes), with three sample object reads checked via
the backend's Vault-loaded configuration. Obsidian reached `Fully synced`
and the restored vault contained 1,561 Markdown files. The NER image was absent
from both machines, so it was rebuilt locally and published; `/healthz` returned
`status: ok` on the NAS.

Final service check: all 13 persistent compose services were running; PostgreSQL,
MinIO, Vault and NER reported healthy. MinIO init exited with code 0 and the
Alembic migration run succeeded. All 12 distinct image copies (including the
registry/UI bootstrap mirrors) were verified between Docker Desktop and the
NAS registry and retained in Container Station Images.

The `scheduled_tasks` row `obsidian_reimport` is now **disabled**; its former
03:30 Europe/Warsaw time is retained. This prevents the restored full-vault
schedule from becoming an unintended post-migration backfill. The coordinator
was started only after initial Obsidian file synchronization completed; its
watcher still supports individual-note jobs. Do not re-enable a full migration
scan in place of the batch procedure.

The original migration backup was retained. The initial empty PostgreSQL
database was preserved as `lenie-ai-empty-before-restore-20260919`; the
incorrectly flattened MinIO copy was preserved separately at
`/share/Container/lenie-compose/minio-before-layout-fix-20260919`. That latter
directory is diagnostic material, **not a valid restore source**.

A private Docker registry (`registry:2`) runs on the NAS to store built images. This replaces the previous workflow of exporting images to `.tar.gz`, transferring via `scp`, and loading with `docker load`.

### One-Time Setup

#### 1. Start registry container on NAS

```bash
ssh admin@192.168.200.7
DOCKER=/share/CACHEDEV2_DATA/.qpkg/container-station/bin/docker

$DOCKER run -d --name lenie-registry \
  --restart unless-stopped \
  -p 5005:5000 \
  -v lenie-registry-data:/var/lib/registry \
  -e REGISTRY_HTTP_HEADERS_Access-Control-Allow-Origin='["*"]' \
  -e REGISTRY_HTTP_HEADERS_Access-Control-Allow-Methods='["HEAD","GET","OPTIONS","DELETE"]' \
  -e REGISTRY_HTTP_HEADERS_Access-Control-Allow-Headers='["Authorization","Accept","Cache-Control"]' \
  -e REGISTRY_HTTP_HEADERS_Access-Control-Expose-Headers='["Docker-Content-Digest"]' \
  -e REGISTRY_STORAGE_DELETE_ENABLED=true \
  registry:2
```

#### 2. Configure insecure-registries

The registry runs without TLS (HTTP only), so both the PC and NAS must allow it as an insecure registry.

This shortcut supports fast local build/push/pull iterations. It requires restricted
network access as described in the [local security profile](../security/local-development-security.md).
An internal registry may also be used in production, but must have transport and
access controls; do not copy this unauthenticated HTTP setup as a production default.

**PC (Docker Desktop):**

Settings → Docker Engine → add to JSON:

```json
{
  "insecure-registries": ["192.168.200.7:5005"]
}
```

Apply & Restart Docker Desktop.

**NAS (Container Station):**

Edit `/share/CACHEDEV2_DATA/.qpkg/container-station/etc/docker.json`, add:

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
DOCKER=/share/CACHEDEV2_DATA/.qpkg/container-station/bin/docker
$DOCKER pull 192.168.200.7:5005/hello-world
```

### Garbage Collection

Over time, the registry accumulates old image layers. To reclaim disk space:

```bash
ssh admin@192.168.200.7
DOCKER=/share/CACHEDEV2_DATA/.qpkg/container-station/bin/docker

# Run garbage collection (removes unreferenced blobs)
$DOCKER exec lenie-registry bin/registry garbage-collect /etc/docker/registry/config.yml

# Check registry disk usage
$DOCKER exec lenie-registry du -sh /var/lib/registry
```

## Deployment

### Automated Deploy Script

`infra/docker/nas-deploy.ps1` (PowerShell, native Windows — no WSL) is the primary deploy path. It builds images, pushes to the private registry, and deploys via `docker compose` using the Windows OpenSSH client directly:

```powershell
# Deploy all core services (build → push → compose up)
.\infra\docker\nas-deploy.ps1

# Deploy specific service(s)
.\infra\docker\nas-deploy.ps1 -Service frontend
.\infra\docker\nas-deploy.ps1 -Service backend,app2

# Push existing image without rebuilding
.\infra\docker\nas-deploy.ps1 -Service backend -SkipBuild

# Only run compose up on NAS (no build/push)
.\infra\docker\nas-deploy.ps1 -ComposeOnly

# Copy compose.nas.yaml to NAS and deploy
.\infra\docker\nas-deploy.ps1 -SyncCompose
```

`infra/docker/nas-deploy.sh` is the older bash equivalent (same steps, same flags in `--flag` form) — kept for Mac/Linux use, not required on Windows anymore.

> **Note:** `minio` is not included in the default `all` target — it must be deployed explicitly. MinIO uses the pinned NAS registry mirror described above; publish that mirror before deployment. The deploy script does not build or publish MinIO itself.

The script performs these steps for each service:

1. Build Docker image locally (faster than on NAS CPU)
2. Tag image for the private registry (`192.168.200.7:5005/...`)
3. Push to registry via `docker push`
4. On NAS: `docker compose pull` to fetch updated images
5. On NAS: `docker compose up -d` to recreate changed containers

### Compose File

The compose file lives at `/share/Container/lenie-compose/compose.nas.yaml` on the NAS. Source of truth is `infra/docker/compose.nas.yaml` in the repo.

To sync it to NAS:

```powershell
.\infra\docker\nas-deploy.ps1 -SyncCompose
# or manually:
scp infra/docker/compose.nas.yaml admin@192.168.200.7:/share/Container/lenie-compose/compose.nas.yaml
```

### Docker Compose Commands on NAS

```bash
ssh admin@192.168.200.7
DOCKER=/share/CACHEDEV2_DATA/.qpkg/container-station/bin/docker

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
   DOCKER=/share/CACHEDEV2_DATA/.qpkg/container-station/bin/docker
   $DOCKER volume create lenie-ai-db-data
   $DOCKER volume create lenie-ai-data
   $DOCKER volume create lenie-minio-data
   ```
6. Stop old containers:
   ```bash
   $DOCKER stop lenie-ai-frontend lenie-ai-app2 lenie-ai-server lenie-ai-db vault
   $DOCKER rm lenie-ai-frontend lenie-ai-app2 lenie-ai-server lenie-ai-db vault
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
DOCKER=/share/CACHEDEV2_DATA/.qpkg/container-station/bin/docker
$DOCKER compose -f /share/Container/lenie-compose/compose.nas.yaml pull
$DOCKER compose -f /share/Container/lenie-compose/compose.nas.yaml up -d
```

## Database Setup

The database container uses a custom image built from `infra/docker/Postgresql/Dockerfile`:
- Base: `postgres:18-bookworm`
- Extension: `postgresql-18-pgvector`
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

Password: the compose default `postgres`, unless `NAS_DB_PASSWORD` was set in
the NAS env file. Database name is **`lenie-ai`** (created by
`01-create-database.sql` above — not the legacy local-dev name `lenie`).

This describes the initialization fallback, not a verification of the live database
password. The fallback is suitable only for an isolated disposable test database;
persistent NAS data requires an individual secret. Changing the Compose variable
does not establish that an existing database password has been rotated. See the
[local security profile](../security/local-development-security.md).

Python one-off/backfill scripts (`backend/imports/*.py`) connect through the
ORM instead of `psql` — for the exact env-var pattern see
`backend/imports/CLAUDE.md` ("Running scripts against the NAS production DB").

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

### Writable cache for media processing

`CACHE_DIR` is application configuration, but in the NAS deployment it is
loaded from Vault together with the remaining application settings. It must be
an absolute path writable by uid `1000`; never use a relative `tmp` path,
because it resolves to `/app/tmp` and the non-root backend user cannot create
it. The durable NAS value is `/app/data/cache`:

```powershell
.\backend\.venv\Scripts\python.exe scripts\env_to_vault.py vault set --env dev CACHE_DIR=/app/data/cache
ssh admin@192.168.200.7 "/share/CACHEDEV2_DATA/.qpkg/container-station/bin/docker exec -u 0 lenie-ai-server sh -c 'mkdir -p /app/data/cache/youtube_to_text && chown -R 1000:1000 /app/data/cache'"
ssh admin@192.168.200.7 "/share/CACHEDEV2_DATA/.qpkg/container-station/bin/docker restart lenie-ai-server"
```

Use the same directory for the other application-side pipelines that use
`CACHE_DIR`. Source HTML/text remains durable in MinIO; this cache holds
working files such as downloaded YouTube media and conversion intermediates.

## Vault

HashiCorp Vault runs on the NAS for secrets management. Auto-unseal is configured via AWS KMS — Vault unseals itself automatically after every NAS restart.

> **Detailed setup:** [Vault_Setup.md](Vault_Setup.md) — full installation, auto-unseal migration, token management.

### Configuration

Config file location on NAS: `/share/vault/config/vault.hcl`

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
- `/share/vault/config` — configuration
- `/share/vault/data` — encrypted storage
- `/share/vault/logs` — logs

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
DOCKER=/share/CACHEDEV2_DATA/.qpkg/container-station/bin/docker
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

### Deploy aborts immediately on the first `docker build` line

Symptom: `nas-deploy.ps1` exits almost instantly with

```
docker : #0 building with "desktop-linux" instance using docker driver
    + CategoryInfo          : NotSpecified: (...) [], RemoteException
    + FullyQualifiedErrorId : NativeCommandError
```

Cause: the script runs under `$ErrorActionPreference = "Stop"`, and `docker
build` writes its progress to **stderr**. In Windows PowerShell 5.1, redirecting
a native command's stderr (`.\nas-deploy.ps1 ... 2>&1`, or piping to
`Tee-Object` after `2>&1`) turns every stderr line into an error record, so the
very first progress line becomes a terminating error before anything is built or
pushed. This is **not** a registry or image-transfer problem.

Fix: run the script without `2>&1`. Run it directly (`.\infra\docker\nas-deploy.ps1
-Service backend,worker`) — PowerShell shows stderr on the console anyway. To
capture a full log, use `*> deploy.log` (merges all streams without the
error-record conversion) or `-RedirectStandardOutput`, never `2>&1`.

### Check container status

```bash
ssh admin@192.168.200.7
DOCKER=/share/CACHEDEV2_DATA/.qpkg/container-station/bin/docker

# Via compose
$DOCKER compose -f /share/Container/lenie-compose/compose.nas.yaml ps

# All lenie containers (including registry)
$DOCKER ps --filter name=lenie
```

### View logs

```bash
$DOCKER compose -f /share/Container/lenie-compose/compose.nas.yaml logs --tail 50 lenie-ai-server
$DOCKER compose -f /share/Container/lenie-compose/compose.nas.yaml logs --tail 50 lenie-worker
$DOCKER compose -f /share/Container/lenie-compose/compose.nas.yaml logs --tail 50 lenie-document-worker
$DOCKER compose -f /share/Container/lenie-compose/compose.nas.yaml logs --tail 50 lenie-ai-db
$DOCKER compose -f /share/Container/lenie-compose/compose.nas.yaml logs --tail 50 lenie-minio
$DOCKER logs --tail 50 lenie-vault
$DOCKER logs --tail 50 lenie-registry
```

### Container keeps restarting

Check logs for errors. Common issues:
- **`ModuleNotFoundError`** in backend — Dockerfile ENTRYPOINT must use venv Python (`/app/.venv/bin/python`)
- **Port already in use** — check with `netstat -tlnp | grep <PORT>`
- **Database connection refused** — ensure DB container is running and healthy (`docker compose ps`)

The document worker's `/app/work` directory is prepared and owned by UID/GID
`1000:1000` in `backend/Dockerfile`. This is required when Docker creates a
fresh external volume `lenie-document-work`; do not remove that ownership fix
from the image. Existing NAS volumes may be repaired without deleting data by
running `docker exec -u 0 lenie-document-worker chown -R 1000:1000 /app/work`.

### Rebuild and redeploy a single service

```powershell
.\infra\docker\nas-deploy.ps1 -Service backend
```

Note which services **share one image**: `backend` (`lenie-ai-server`),
`worker`, `cloud-bridge` and `lenie-migrate` all run `lenie-ai-server:latest`;
`document-worker` has its own tag (adds the markdown extra). Deploying
`backend` therefore **also recreates `worker` and `cloud-bridge`** (the script adds
them and prints what it added; the image is built and pushed once), so none of
them keeps running stale code. Pass `-NoImplied` (`--no-implied` for the bash
script) to deploy exactly the services you named. `document-worker` is never added
implicitly — name it too when the change affects document preparation; the script
prints a reminder.

### SSH connection timeouts during deploy

QNAP sshd occasionally takes longer than a few seconds to accept a connection
even when the NAS is healthy (`ssh: connect to host 192.168.200.7 port 22:
Connection timed out`). `nas-deploy.ps1` probes SSH with a 15 s timeout and
retries 3× before giving up. If a later step still dies on a timeout, simply
re-run the script — build/push/compose steps are idempotent — or finish
manually per "Manual Deploy (Step by Step)" above.

### Disk space on NAS

```bash
ssh admin@192.168.200.7 'df -h /share/CACHEDEV2_DATA'
```

Inspect Docker disk usage on NAS:

```bash
$DOCKER system df
```

Do not run blanket `system prune -a` or `image prune -a`: images without a
running container can still be the recovery copies for registry, migrations
or MinIO init. Remove only individually reviewed obsolete image references,
after verifying that every required recovery image exists elsewhere.

### Docker Desktop / NAS Docker version drift breaks save/scp/load

2026-07-27: local Docker Desktop had auto-updated to 29.6.1 while the NAS
(Container Station) stayed on 27.1.2-qnap8. This broke the save/scp/load
fallback path (`nas-deploy.ps1`/`.sh`'s `push_image` used it unconditionally
at the time): newer `docker save` emits an OCI-layout tar (`blobs/sha256/...`,
no legacy `manifest.json`/per-layer folders), which the older `docker load`
can't parse — symptoms seen, in order of attempted workaround: `archive/tar:
invalid tar header` (plain save), same error with `--provenance=false
--sbom=false`, `flate: corrupt input before offset ...` (via `docker buildx
build --output type=docker`), and finally `invalid diffID for layer N`
(after disabling Docker Desktop's containerd image store in Settings →
General — this changes the local storage driver back to `overlay2` but does
**not** change `docker save`'s output format, so it didn't help).

**What actually fixed it:** switching to a direct `docker push` to the NAS
registry (`docker tag ... 192.168.200.7:5005/...; docker push ...`) instead of
save/scp/load — this uses the OCI Distribution (registry) API, which stayed
compatible across the version gap even though the raw tar format did not. This
required re-adding `"insecure-registries": ["192.168.200.7:5005"]` to Docker
Desktop's Docker Engine JSON (see [Configure insecure-registries](#2-configure-insecure-registries)
above) — it had been lost, most likely by the Docker Desktop update/reset.
Worked for both a ~1.1GB backend image and the Alpine-based frontend image
(no recurrence of the checksum bug below on this attempt).

**Takeaway for next time:** if `nas-deploy.ps1`/`.sh` suddenly fails on image
publish, check `docker version` locally vs. `ssh admin@192.168.200.7
"/share/CACHEDEV2_DATA/.qpkg/container-station/bin/docker version"` for a
version gap before deep-diagnosing tar/checksum errors — and check that
insecure-registries is still configured (Docker Desktop updates can reset it).
The deploy scripts now default to direct push with an automatic fallback to
save/scp/load if push fails, but that fallback is exactly the path that broke
here, so it won't rescue you from this specific failure mode again.

### docker push fails with "file integrity checksum failed"

Known issue with Docker Desktop on Windows — `docker push` (and `docker save`) may fail with `file integrity checksum failed for "etc/apk/..."` for images using Alpine-based base images (e.g. `nginx:alpine`). The Docker Desktop storage layer becomes corrupted.

**Fix:** Prune builder cache and rebuild with fresh base images:

```bash
docker builder prune -f
docker build --no-cache --pull -t 192.168.200.7:5005/lenie-ai-frontend:latest -f web_interface_react/Dockerfile .
docker push 192.168.200.7:5005/lenie-ai-frontend:latest
```

If the problem persists, restart Docker Desktop (Settings → Resources → Restart).

**Alternative (bypass registry):** Transfer image directly via SSH:

```bash
docker save 192.168.200.7:5005/lenie-ai-frontend:latest | \
  ssh admin@192.168.200.7 \
  "/share/CACHEDEV2_DATA/.qpkg/container-station/bin/docker load"
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
