# Story 22.1: NAS Deployment & End-to-End Verification

Status: in-progress

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **developer**,
I want to deploy the Slack Bot to NAS with full Docker Compose infrastructure (registry, MinIO, compose migration),
So that I have a repeatable deployment pipeline and confidence the MVP works on a real environment.

## Acceptance Criteria

1. **Given** the NAS has Docker and existing containers running individually
   **When** developer sets up the Docker registry, updates compose.nas.yaml, and runs `nas-deploy.sh`
   **Then** all services (including Slack Bot and MinIO) run via Docker Compose on `lenie-net` network

2. **Given** the private Docker registry is running on NAS
   **When** developer runs `./infra/docker/nas-deploy.sh slack-bot`
   **Then** the image is built locally, pushed to registry, pulled on NAS, and container starts

3. **Given** the bot is running on NAS with real backend
   **When** user types each of the 5 slash commands in Slack
   **Then** all commands return correct data from the real backend

4. **Given** MinIO is running on NAS
   **When** developer accesses `http://192.168.200.7:9001`
   **Then** MinIO web console is accessible and `website-content` bucket exists

5. **Given** deployment procedure is verified
   **When** developer documents the process
   **Then** `docs/CICD/NAS_Deployment.md` reflects the current state

**Covers:** FR21, FR24 | NFR2, NFR5, NFR8

## Tasks / Subtasks

### Part A: Docker Registry Setup

- [x] Task 1: Start private Docker registry on NAS (AC: #2)
  - [x] 1.1: SSH to NAS, start registry container (registry:2 on port 5005, volume lenie-registry-data)
  - [x] 1.2: Configure insecure-registries on NAS docker.json
  - [x] 1.3: Configure insecure-registries on PC (Docker Desktop UI)
  - [x] 1.4: Verify push/pull to registry — all service images pushed successfully

### Part B: Infrastructure Files Update

- [x] Task 2: Add Slack Bot and MinIO to `compose.nas.yaml` (AC: #1, #4)
  - [x] 2.1: Add `lenie-ai-slack-bot` service — image from registry, env_file, lenie-net, depends_on server, no ports
  - [x] 2.2: Add `lenie-minio` service — MinIO single-node, ports 9000:9000 + 9001:9001, volume for data, lenie-net, healthcheck
  - [x] 2.3: Add `lenie-minio-data` volume (external: true)
  - [x] 2.4: Ensure Vault container name matches current NAS (`vault` → decide whether to rename to `lenie-vault` or keep as-is)
  - [x] 2.5: Validate YAML syntax

- [x] Task 3: Add `slack-bot` and `minio` service mappings to `nas-deploy.sh` (AC: #2)
  - [x] 3.1: Add `slack-bot` to `SVC_IMAGE`, `SVC_REGISTRY_IMAGE`, `SVC_DOCKERFILE`, `SVC_COMPOSE_NAME`
  - [x] 3.2: Add `minio` to `SVC_IMAGE`, `SVC_REGISTRY_IMAGE`, `SVC_COMPOSE_NAME` — NOTE: MinIO uses official image (no Dockerfile, no build step), so `SVC_DOCKERFILE` entry is not needed. Handle `--skip-build` logic or pull directly
  - [x] 3.3: Do NOT add `slack-bot` or `minio` to `ALL_SERVICES` — deploy explicitly (opt-in)
  - [x] 3.4: Verify script works for existing services after changes

- [x] Task 4: Update `nas.env.example` with new variables (AC: #5)
  - [x] 4.1: Add Slack variables: `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, `SLACK_CHANNEL_STARTUP`
  - [x] 4.2: Add MinIO variables: `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`, `S3_ENDPOINT_URL`

### Part C: NAS Configuration

- [x] Task 5: Configure NAS secrets via Vault backend (AC: #1, #3)
  - [x] 5.1: Migrated NAS from SECRETS_BACKEND=env to SECRETS_BACKEND=vault — minimal .env with bootstrap vars only (SECRETS_BACKEND, SECRETS_ENV, PROJECT_CODE, VAULT_ADDR, VAULT_TOKEN)
  - [x] 5.2: Added Slack tokens (SLACK_BOT_TOKEN, SLACK_APP_TOKEN, SLACK_CHANNEL_STARTUP) to Vault secret/lenie/dev
  - [x] 5.3: Added MinIO credentials (MINIO_ROOT_USER, MINIO_ROOT_PASSWORD, S3_ENDPOINT_URL) to Vault secret/lenie/dev
  - [x] 5.4: Created minio.env file at /share/Container/lenie-env/minio.env (MinIO reads env directly, not via Vault)
  - [x] 5.5: Created MinIO data volume: `docker volume create lenie-minio-data`

### Part D: Deploy to NAS

- [x] Task 6: Sync compose file and deploy (AC: #1, #2)
  - [x] 6.1: Synced compose.nas.yaml to NAS /share/Container/lenie-compose/
  - [x] 6.2: Built and pushed all images to registry (server, slack-bot, db, frontend, app2)
  - [x] 6.3: Stopped old individually-managed containers and migrated to Docker Compose
  - [x] 6.4: All 7 containers running via `compose up -d`: db(healthy), server(up), frontend(up), app2(up), slack-bot(up), minio(healthy), vault(healthy)
  - [x] 6.5: Created MinIO bucket `website-content` via `mc mb local/website-content`
  - [x] 6.6: Full Compose migration completed — all services managed by compose.nas.yaml

### Part E: Slack Bot Verification

- [ ] Task 7: Verify startup and slash commands (AC: #3)
  - [x] 7.1: Check Slack channel for startup message — confirmed: "Startup message posted to #all-lenie-ai", backend version 0.3.13.0
  - [ ] 7.2: `/lenie-version` — verify real backend version (manual test needed)
  - [ ] 7.3: `/lenie-count` — verify real document count (manual test needed)
  - [ ] 7.4: `/lenie-add https://example.com/test-story-22-1` — verify URL added (manual test needed)
  - [ ] 7.5: `/lenie-check https://example.com/test-story-22-1` — verify found (manual test needed)
  - [ ] 7.6: `/lenie-info <id>` — verify document details (manual test needed)
  - [ ] 7.7: Error cases: `/lenie-info abc`, `/lenie-add` (no URL) (manual test needed)

- [ ] Task 8: Fix integration issues if found (AC: #3)
  - [ ] 8.1: If API response mismatch (KeyError) — fix in `commands.py` or `api_client.py`
  - [ ] 8.2: After code fixes — run tests: `cd slack_bot && PYTHONPATH=. .venv/Scripts/python -m pytest tests/unit/ -v`
  - [ ] 8.3: Rebuild and redeploy: `./infra/docker/nas-deploy.sh slack-bot`

### Part F: MinIO Verification

- [ ] Task 9: Verify MinIO (AC: #4)
  - [ ] 9.1: Access MinIO console: `http://192.168.200.7:9001` — login with MINIO_ROOT_USER/PASSWORD
  - [ ] 9.2: Verify `website-content` bucket exists
  - [ ] 9.3: Test S3 API from backend container:
    ```bash
    $DOCKER exec lenie-ai-server python -c "import boto3; s3=boto3.client('s3', endpoint_url='http://lenie-minio:9000', aws_access_key_id='lenie-admin', aws_secret_access_key='<pw>'); print(s3.list_buckets())"
    ```

### Part G: Documentation

- [x] Task 10: Update documentation (AC: #5)
  - [x] 10.1: Update `docs/CICD/NAS_Deployment.md` — add Slack Bot and MinIO to Stack Overview, update deployment instructions to use `nas-deploy.sh`
  - [x] 10.2: Update `infra/docker/nas.env.example` with Slack + MinIO placeholders
  - [x] 10.3: Document registry setup status and verify instructions

## Dev Notes

### Scope Overview

This story has three infrastructure goals plus verification:
1. **Docker Registry** — enable `nas-deploy.sh` workflow (build on PC → push → pull on NAS)
2. **Slack Bot deployment** — add to compose, deploy, verify all 5 commands
3. **MinIO** — S3-compatible local storage for HTML files (container + bucket only, backend code integration is separate future work)
4. **Compose migration** — transition from individual containers to Docker Compose management

### NAS Environment — Current State (Verified via SSH 2026-03-02)

**Hardware:** QNAP TS-453Be, Intel Celeron J3455, 16 GB RAM, QTS Linux 5.10, Docker 27.x

**Running containers** (all individually managed, NOT via Docker Compose):

| Container | Status | Port | Network |
|-----------|--------|------|---------|
| `lenie-ai-db` | Up 4 days | 5434:5432 | lenie-net |
| `lenie-ai-server` | Up 4 days | 5055:5000 | lenie-net |
| `lenie-ai-frontend` | Up 4 days | 3000:80 | default |
| `lenie-ai-app2` | Up 4 days | 3001:80 | default |
| `vault` | Up 3 days | 8210:8200 | default |

**Not running:** `lenie-registry` (Docker registry), `lenie-minio` (MinIO)
**Not deployed:** `compose.nas.yaml` — file does not exist on NAS at `/share/Container/lenie-compose/`
**Free ports confirmed:** 5005, 9000, 9001

**Docker path on QNAP:**
```
DOCKER=/share/CACHEDEV1_DATA/.qpkg/container-station/usr/bin/.libs/docker
```

**NAS directories:**
```
/share/Container/
├── lenie-env/          .env file (secrets in plaintext, env backend)
├── vault/              Vault config + data + logs
├── lenie-db-build/     DB build context
└── container-station-data/  Container Station internal
```

### Target State After Story

```
NAS (QNAP TS-453Be) — All managed via Docker Compose (compose.nas.yaml)

Services:
├── lenie-ai-db           PostgreSQL 17 + pgvector        5434:5432    lenie-net
├── lenie-ai-server       Flask backend                   5055:5000    lenie-net
├── lenie-ai-slack-bot    Slack Bot (Socket Mode)          no port      lenie-net  ← NEW
├── lenie-ai-frontend     React SPA (nginx)                3000:80      lenie-net
├── lenie-ai-app2         Admin Panel (nginx)              3001:80      lenie-net
├── lenie-vault           HashiCorp Vault                  8210:8200    lenie-net
└── lenie-minio           MinIO S3-compatible storage      9000+9001    lenie-net  ← NEW

Infrastructure (standalone, not in compose):
└── lenie-registry        Docker registry                  5005:5000    (host)
```

### compose.nas.yaml — Services to Add

**Slack Bot:**
```yaml
  lenie-ai-slack-bot:
    image: 192.168.200.7:5005/lenie-ai-slack-bot:latest
    container_name: lenie-ai-slack-bot
    restart: unless-stopped
    env_file:
      - /share/Container/lenie-env/.env
    networks:
      - lenie-net
    depends_on:
      - lenie-ai-server
```

**MinIO:**
```yaml
  lenie-minio:
    image: minio/minio:latest
    container_name: lenie-minio
    restart: unless-stopped
    ports:
      - "9000:9000"   # S3 API
      - "9001:9001"   # Web console
    environment:
      MINIO_ROOT_USER: ${MINIO_ROOT_USER:-lenie-admin}
      MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD:-changeme}
    command: server /data --console-address ":9001"
    volumes:
      - lenie-minio-data:/data
    networks:
      - lenie-net
    healthcheck:
      test: ["CMD", "mc", "ready", "local"]
      interval: 30s
      timeout: 5s
      retries: 3
```

### nas-deploy.sh — Mappings to Add

```bash
# Slack Bot
[slack-bot]="lenie-ai-slack-bot:latest"           # SVC_IMAGE
[slack-bot]="${REGISTRY}/lenie-ai-slack-bot:latest" # SVC_REGISTRY_IMAGE
[slack-bot]="slack_bot/Dockerfile"                  # SVC_DOCKERFILE
[slack-bot]="lenie-ai-slack-bot"                    # SVC_COMPOSE_NAME

# MinIO — uses official image, NO Dockerfile
# Handle in deploy script: skip build, pull official image directly
```

**MinIO handling:** MinIO uses `minio/minio:latest` from Docker Hub, not from the private registry. The deploy script needs to handle services without a Dockerfile (skip build+push, only pull+deploy). Options:
- (A) Add `minio` to `SVC_COMPOSE_NAME` only, skip build/push — just `compose pull` + `compose up`
- (B) Don't add to `nas-deploy.sh` at all — manage MinIO via `docker compose pull/up` directly

### Docker Compose Migration Strategy

Currently all 5 containers run individually. The migration to Compose must:

1. **Sync compose.nas.yaml** to NAS (`--sync-compose`)
2. **Stop old individual containers** (they'll conflict with compose-managed ones):
   ```bash
   $DOCKER stop lenie-ai-frontend lenie-ai-app2 lenie-ai-server lenie-ai-db vault
   $DOCKER rm lenie-ai-frontend lenie-ai-app2 lenie-ai-server lenie-ai-db vault
   ```
3. **Create external volumes** if they don't exist:
   ```bash
   $DOCKER volume create lenie-ai-db-data
   $DOCKER volume create lenie-ai-data
   $DOCKER volume create lenie-minio-data
   ```
4. **Start all via Compose**: `$DOCKER compose -f /share/Container/lenie-compose/compose.nas.yaml up -d`

**Risk:** Vault container name changes from `vault` to `lenie-vault` (as in compose.nas.yaml). If backend .env uses `VAULT_ADDR=http://vault:8200`, it must be updated to `http://lenie-vault:8200`. However, the current NAS uses `SECRETS_BACKEND=env` (not Vault), so this is low risk.

**Data safety:** DB data is in Docker volume `lenie-ai-db-data`. If the volume is `external: true` in compose, it won't be destroyed by `compose down`. Verify volume exists before stopping old containers.

### Configuration Variables

| Variable | In NAS .env? | Required? | Notes |
|----------|-------------|-----------|-------|
| `SLACK_BOT_TOKEN` | NO — add | Yes | `xoxb-...` from Slack App OAuth |
| `SLACK_APP_TOKEN` | NO — add | Yes | `xapp-...` from Slack App Basic Info |
| `STALKER_API_KEY` | YES | Yes | Bot uses for `x-api-key` header |
| `LENIE_API_URL` | NO (code default) | No | Defaults to `http://lenie-ai-server:5000` |
| `SLACK_CHANNEL_STARTUP` | NO (code default) | No | Defaults to `#general` |
| `MINIO_ROOT_USER` | NO — add | Yes | MinIO admin username |
| `MINIO_ROOT_PASSWORD` | NO — add | Yes | MinIO admin password |
| `S3_ENDPOINT_URL` | NO — add | For future use | `http://lenie-minio:9000` |

### Known Risk: API Response Field Names

**#1 integration risk for Slack Bot.** Bot developed with mocked responses — real backend may differ:

| Handler | File:Line | Expected Keys |
|---------|-----------|---------------|
| `/lenie-version` | `commands.py:34` | `data['app_version']`, `data['app_build_time']` |
| `/lenie-add` | `commands.py:78` | `data['document_id']` |
| `/lenie-check` | `commands.py:102-105` | `result['id']`, `result['document_type']`, `result['document_state']`, `result['created_at']` |
| `/lenie-info` | `commands.py:136-140` | `data['title']`, `data['document_type']`, `data['document_state']`, `data['created_at']` |

If any key missing/renamed → bot logs `KeyError`, shows "Unexpected response from backend" (safe, no crash). Fix by aligning field names.

### Testing Strategy

1. **Slack Bot smoke tests**: Run each slash command in Slack, verify correct output
2. **MinIO verification**: Access web console, verify bucket, test S3 API from backend container
3. **Compose verification**: `compose ps` shows all services running
4. **Regression check after code fixes**:
   ```bash
   cd slack_bot && PYTHONPATH=. .venv/Scripts/python -m pytest tests/unit/ -v
   ```
   Expected: 100 tests (do NOT use `uvx pytest` — needs venv)

### MinIO — Scope Boundary

This story sets up MinIO **infrastructure only** (container + bucket). Backend code integration (updating boto3 clients to use `S3_ENDPOINT_URL`, migrating `dynamodb_sync.py` to upload to MinIO) is **separate future work** tracked as B-82. The S3_ENDPOINT_URL variable is added to .env for future use.

### Previous Epic Intelligence (Epic 21 Retrospective)

1. **"Deploy before building new features"** — Why this story exists
2. **Repeated unsafe dict access** — KeyError handlers in place, real responses may trigger them
3. **Test runner** — `.venv/Scripts/python -m pytest`, NOT `uvx pytest`
4. **Closure pattern** — `register_commands()` stable, do not change

### Git Intelligence

Recent commits:
- `64d676d` — backend connectivity check in Slack bot startup
- `4a5866a` — vault+aws extras in Slack bot Dockerfile
- `61077f0` — Slack Bot MVP (Epic 21)
- `7d11b12` — shared unified-config-loader package

### Project Structure Notes

**Files to create/modify:**

| File | Action |
|------|--------|
| `infra/docker/compose.nas.yaml` | MODIFY — add slack-bot + minio services, minio volume |
| `infra/docker/nas-deploy.sh` | MODIFY — add slack-bot + minio service mappings |
| `infra/docker/nas.env.example` | MODIFY — add Slack + MinIO variable placeholders |
| `docs/CICD/NAS_Deployment.md` | MODIFY — add Slack Bot + MinIO to stack docs, update deploy instructions |

**Files potentially modified (only if integration bugs):**
| `slack_bot/src/commands.py` | response field name fixes |
| `slack_bot/src/api_client.py` | request format fixes |

### References

- [Source: docs/CICD/NAS_Deployment.md] — NAS hardware, Docker paths, registry setup, compose commands
- [Source: infra/docker/compose.nas.yaml] — Current NAS compose (no slack-bot/minio yet)
- [Source: infra/docker/nas-deploy.sh] — Build/push/deploy script
- [Source: infra/docker/nas.env.example] — NAS env template
- [Source: _bmad-output/planning-artifacts/epics.md#Story 22.1] — Story definition, acceptance criteria
- [Source: _bmad-output/planning-artifacts/epics/backlog.md#B-82] — MinIO backlog item with full scope
- [Source: _bmad-output/implementation-artifacts/epic-21-retro-2026-03-02.md] — Deployment-first rationale
- [Source: _bmad-output/planning-artifacts/prd.md#Technical Context] — Architecture, API communication
- [Source: slack_bot/src/main.py] — Entry point, Socket Mode, startup message
- [Source: slack_bot/src/api_client.py] — HTTP client, exception hierarchy
- [Source: slack_bot/src/commands.py] — 5 slash command handlers
- [Source: slack_bot/Dockerfile] — Docker build with shared package

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- **Task 1 (Registry):** Started registry:2 container on NAS port 5005 with persistent volume. Configured insecure-registries on both NAS (docker.json) and PC (Docker Desktop UI). Verified push/pull works.
- **Task 2 (compose.nas.yaml):** Added `lenie-ai-slack-bot` service (registry image, env_file, lenie-net, depends_on server) and `lenie-minio` service (official minio/minio:latest, ports 9000+9001, healthcheck, external volume). Added `lenie-minio-data` volume. Fixed Vault mount paths from `/share/Container/vault/` to `/share/vault/`. Changed MinIO env from `${MINIO_*}` interpolation to `env_file: minio.env`.
- **Task 3 (nas-deploy.sh):** Added `slack-bot` to all 4 service arrays. Added `minio` to COMPOSE_NAME only. Modified `deploy_service()` to skip build/push when no SVC_DOCKERFILE. NOT added to ALL_SERVICES (opt-in only).
- **Task 4 (nas.env.example):** Added Slack + MinIO variable placeholders. Updated VAULT_ADDR to `http://lenie-vault:8200`.
- **Task 5 (NAS config):** Migrated NAS from SECRETS_BACKEND=env to SECRETS_BACKEND=vault. Minimal .env (5 bootstrap vars). All app secrets in Vault secret/lenie/dev (61 variables). Created separate minio.env for MinIO container (can't use Vault). Created lenie-minio-data volume.
- **Task 6 (Deploy):** Full Compose migration completed. Stopped old individual containers, started all 7 via `compose up -d`. Fixed stale Docker image issue (old code without unified_config_loader) by rebuilding and pushing server + slack-bot images. Fixed slack-bot Dockerfile missing README.md (hatchling build error).
- **Task 10 (documentation):** Updated NAS_Deployment.md with Slack Bot + MinIO in Stack Overview, deploy instructions, troubleshooting.
- **Remaining:** Task 6.5 (MinIO bucket creation), Task 7.2-7.7 (manual Slack command verification), Task 9 (MinIO verification).

### Implementation Notes

- MinIO deploy strategy: Option A chosen — `minio` added to SVC_COMPOSE_NAME, deploy script detects missing SVC_DOCKERFILE and skips build/push automatically. `./nas-deploy.sh minio` triggers compose pull+up only.
- Vault name decision (subtask 2.4): Kept `lenie-vault` as already defined in compose. Updated nas.env.example VAULT_ADDR accordingly. Low risk since NAS uses `SECRETS_BACKEND=env`.
- Slack Bot tests: 106 passed (all green). Backend tests: 6 pre-existing failures unrelated to this story.

### File List

- `infra/docker/compose.nas.yaml` — MODIFIED (added slack-bot + minio services, minio volume, fixed vault mount paths, minio env_file)
- `infra/docker/nas-deploy.sh` — MODIFIED (added slack-bot + minio mappings, skip-build logic for official images)
- `infra/docker/nas.env.example` — MODIFIED (added Slack + MinIO variables, updated VAULT_ADDR)
- `slack_bot/Dockerfile` — MODIFIED (added missing README.md COPY for hatchling build)
- `docs/CICD/NAS_Deployment.md` — MODIFIED (added Slack Bot + MinIO to stack docs, deploy instructions, troubleshooting)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — MODIFIED (22-1 status: ready-for-dev → in-progress, added B-83)
- `_bmad-output/implementation-artifacts/22-1-nas-deployment-end-to-end-verification.md` — MODIFIED (tasks 1-6,10 marked complete, Dev Agent Record updated)

## Change Log

- 2026-03-02: Implemented infrastructure file changes (Tasks 2, 3, 4, 10) — compose.nas.yaml updated with Slack Bot + MinIO, nas-deploy.sh extended with new service support, nas.env.example updated, NAS_Deployment.md documentation refreshed.
- 2026-03-02: Completed NAS deployment (Tasks 1, 5, 6). Registry setup, Vault-based secrets migration, full Docker Compose migration. All 7 containers running. Fixed stale images (rebuilt with unified_config_loader). Fixed slack-bot Dockerfile (missing README.md). Backend: 427 documents loaded, connected to DB. Slack Bot: Socket Mode connected, startup message posted. Added B-83 for Vault auto-unseal.
