#!/bin/bash
set -euo pipefail

# ============================================================================
# NAS Deploy Script - Build, push to registry, and deploy via Docker Compose
# Usage:
#   ./nas-deploy.sh                          # Build, push & deploy all services
#   ./nas-deploy.sh frontend                 # Build, push & deploy frontend only
#   ./nas-deploy.sh backend app2             # Build, push & deploy backend + app2
#   ./nas-deploy.sh --skip-build frontend    # Push existing image & deploy
#   ./nas-deploy.sh --compose-only           # Only run compose up on NAS
#   ./nas-deploy.sh --sync-compose           # Copy compose.nas.yaml to NAS
# ============================================================================

# --- Configuration ---
NAS_HOST="192.168.200.7"
NAS_USER="admin"
NAS_DOCKER="/share/CACHEDEV4_DATA/.qpkg/container-station/bin/docker"
NAS_COMPOSE_DIR="/share/ContainerNew/lenie-compose"
NAS_COMPOSE_FILE="${NAS_COMPOSE_DIR}/compose.nas.yaml"
NAS_CONFIG_DIR="/share/ContainerNew/lenie-config"
REGISTRY="${NAS_HOST}:5005"

# Project root (two levels up from this script)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOCAL_COMPOSE_FILE="${SCRIPT_DIR}/compose.nas.yaml"
LOCAL_SITE_RULES_FILE="${PROJECT_ROOT}/backend/data/site_rules.json"

# Service definitions: name | local image | registry image | dockerfile
# worker / cloud-bridge share the backend image (lenie-ai-server:latest) and
# have no own Dockerfile entry — a backend code change must be deployed as
# `backend worker cloud-bridge` so `backend` does the single build and the
# others just get pulled + recreated.
declare -A SVC_IMAGE=(
    [frontend]="lenie-ai-frontend:latest"
    [app2]="lenie-ai-app2:latest"
    [backend]="lenie-ai-server:latest"
    [worker]="lenie-ai-server:latest"
    [cloud-bridge]="lenie-ai-server:latest"
    [document-worker]="lenie-ai-document-worker:latest"
    [db]="lenie-ai-db:latest"
    [ner-service]="lenie-ner-service:latest"
)
declare -A SVC_REGISTRY_IMAGE=(
    [frontend]="${REGISTRY}/lenie-ai-frontend:latest"
    [app2]="${REGISTRY}/lenie-ai-app2:latest"
    [backend]="${REGISTRY}/lenie-ai-server:latest"
    [worker]="${REGISTRY}/lenie-ai-server:latest"
    [cloud-bridge]="${REGISTRY}/lenie-ai-server:latest"
    [document-worker]="${REGISTRY}/lenie-ai-document-worker:latest"
    [db]="${REGISTRY}/lenie-ai-db:latest"
    [ner-service]="${REGISTRY}/lenie-ner-service:latest"
)
declare -A SVC_DOCKERFILE=(
    [frontend]="web_interface_react/Dockerfile"
    [app2]="web_interface_app2/Dockerfile"
    [backend]="backend/Dockerfile"
    [document-worker]="backend/Dockerfile"
    [db]="infra/docker/Postgresql/Dockerfile"
    [ner-service]="ner_service/Dockerfile"
)
declare -A SVC_COMPOSE_NAME=(
    [frontend]="lenie-ai-frontend"
    [app2]="lenie-ai-app2"
    [backend]="lenie-ai-server"
    [worker]="lenie-worker"
    [cloud-bridge]="lenie-cloud-bridge"
    [document-worker]="lenie-document-worker"
    [db]="lenie-ai-db"
    [minio]="lenie-minio"
    [ner-service]="lenie-ner-service"
    [obsidian-headless-sync]="obsidian-headless-sync"
)

ALL_SERVICES="db backend worker document-worker frontend app2"

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()   { echo -e "${BLUE}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# --- Functions ---
nas_ssh() {
    ssh -o ConnectTimeout=5 "${NAS_USER}@${NAS_HOST}" "$@"
}

nas_docker() {
    nas_ssh "${NAS_DOCKER} $*"
}

check_nas_connection() {
    log "Sprawdzanie połączenia z NAS ($NAS_HOST)..."
    if ! nas_ssh "echo ok" &>/dev/null; then
        error "Nie można połączyć się z NAS ($NAS_HOST). Sprawdź klucz SSH."
    fi
    ok "Połączenie z NAS OK"
}

check_docker_local() {
    log "Sprawdzanie lokalnego Docker..."
    if ! docker info &>/dev/null; then
        error "Docker Desktop nie jest uruchomiony."
    fi
    ok "Docker lokalny OK"
}

check_registry() {
    log "Sprawdzanie registry (${REGISTRY})..."
    if ! curl -s --connect-timeout 5 "http://${REGISTRY}/v2/" &>/dev/null; then
        error "Registry niedostępne na ${REGISTRY}. Uruchom registry na NAS (patrz docs/CICD/NAS_Deployment.md)."
    fi
    ok "Registry ${REGISTRY} OK"
}

build_image() {
    local svc="$1"
    local image="${SVC_IMAGE[$svc]}"
    local dockerfile="${SVC_DOCKERFILE[$svc]}"

    log "Budowanie obrazu: ${image} (${dockerfile})..."
    cd "$PROJECT_ROOT"
    # Plain progress remains readable in non-interactive Codex/CI logs and
    # makes long dependency/export steps visible instead of buffering them.
    if [ "$svc" = "document-worker" ]; then
        docker build --progress=plain --build-arg 'UV_EXTRA_ARGS=--extra docker --extra markdown' -t "$image" -f "$dockerfile" .
    else
        docker build --progress=plain -t "$image" -f "$dockerfile" .
    fi
    ok "Obraz ${image} zbudowany"
}

# Direct `docker push` to the NAS registry is the primary, documented method
# (docs/CICD/NAS_Deployment.md) — requires the registry configured as an
# insecure-registry in Docker Desktop's daemon.json:
#   "insecure-registries": ["192.168.200.7:5005"]
# Falls back to save -> scp -> load-on-NAS -> local-push (avoids a cross-network
# push entirely) if the direct push fails. Covers two known intermittent Docker
# Desktop bugs: "server gave HTTP response to HTTPS client" (insecure-registries
# config lost, e.g. after a Docker Desktop update) and "file integrity checksum
# failed for etc/apk/..." on Alpine-based images (storage layer corruption, see
# docs/CICD/NAS_Deployment.md's troubleshooting section for the manual fix).
# NOTE (2026-07-27): this fallback itself broke when local Docker Desktop was on
# 29.6.1 vs the NAS's 27.1.2 - newer `docker save` emits an OCI blobs/ layout the
# older `docker load` can't read ("invalid tar header" / "invalid diffID"). If
# direct push ever fails again, check Docker Desktop's version drift from the
# NAS before assuming this fallback will save you.
push_image() {
    local svc="$1"
    local image="${SVC_IMAGE[$svc]}"
    local registry_image="${SVC_REGISTRY_IMAGE[$svc]}"

    log "Push obrazu ${registry_image}..."
    docker tag "$image" "$registry_image"
    if docker push "$registry_image"; then
        ok "Obraz ${registry_image} w registry"
        return
    fi

    warn "Bezpośredni push nie powiódł się dla ${svc} — fallback save/scp/load-na-NAS"
    local archive_name="lenie-deploy-${svc}-$(date +%s)-$$.tar"
    local local_archive="$(mktemp -p /tmp "${archive_name}.XXXXXX")"
    local remote_archive="${NAS_COMPOSE_DIR}/${archive_name}"
    trap 'rm -f "$local_archive"' RETURN

    log "Eksport obrazu ${image} do archiwum..."
    docker save -o "$local_archive" "$image"
    log "Transfer obrazu ${svc} na NAS..."
    scp "$local_archive" "${NAS_USER}@${NAS_HOST}:${remote_archive}"
    log "Ładowanie i publikacja obrazu ${registry_image} na NAS..."
    nas_ssh "${NAS_DOCKER} load -i ${remote_archive} && ${NAS_DOCKER} tag ${image} ${registry_image} && ${NAS_DOCKER} push ${registry_image} && rm -f ${remote_archive}"
    rm -f "$local_archive"
    trap - RETURN
    ok "Obraz ${registry_image} w registry (fallback)"
}

deploy_on_nas() {
    local services_to_pull="$1"

    log "Pulling i restartowanie na NAS..."

    if [ -n "$services_to_pull" ]; then
        # Pull only specified services
        for svc in $services_to_pull; do
            local compose_name="${SVC_COMPOSE_NAME[$svc]}"
            log "Pull: ${compose_name}..."
            nas_docker "compose -f ${NAS_COMPOSE_FILE} pull ${compose_name}"
        done
        # Recreate only the specified services
        local compose_names=""
        for svc in $services_to_pull; do
            compose_names="${compose_names} ${SVC_COMPOSE_NAME[$svc]}"
        done
        nas_docker "compose -f ${NAS_COMPOSE_FILE} up -d ${compose_names}"
    else
        # Pull and deploy everything
        nas_docker "compose -f ${NAS_COMPOSE_FILE} pull"
        nas_docker "compose -f ${NAS_COMPOSE_FILE} up -d"
    fi

    ok "Deploy na NAS zakończony"
}

sync_compose() {
    log "Kopiowanie compose.nas.yaml na NAS..."
    nas_ssh "mkdir -p ${NAS_COMPOSE_DIR}"
    scp "$LOCAL_COMPOSE_FILE" "${NAS_USER}@${NAS_HOST}:${NAS_COMPOSE_FILE}"
    ok "compose.nas.yaml skopiowany do ${NAS_COMPOSE_FILE}"
}

sync_site_rules() {
    log "Kopiowanie site_rules.json na NAS..."
    nas_ssh "mkdir -p ${NAS_CONFIG_DIR}"
    scp "$LOCAL_SITE_RULES_FILE" "${NAS_USER}@${NAS_HOST}:${NAS_CONFIG_DIR}/site_rules.json"
    ok "site_rules.json skopiowany do ${NAS_CONFIG_DIR}"
}

deploy_service() {
    local svc="$1"
    local skip_build="$2"

    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}  Deploying: ${svc}${NC}"
    echo -e "${BLUE}========================================${NC}"

    # No Dockerfile entry means either an official image (minio) or a service
    # that reuses another's build (worker/cloud-bridge share lenie-ai-server,
    # built via `backend`) — nothing to build here, just pull + recreate later.
    if [ -z "${SVC_DOCKERFILE[$svc]:-}" ]; then
        if [ -n "${SVC_IMAGE[$svc]:-}" ]; then
            log "Serwis ${svc} współdzieli obraz ${SVC_IMAGE[$svc]} — buduj go przez 'backend'"
        else
            log "Serwis ${svc} używa oficjalnego obrazu — pomijanie build/push"
        fi
        ok "Deploy ${svc} — rekreacja przy 'compose up' na NAS"
        return
    fi

    if [ "$skip_build" = "false" ]; then
        build_image "$svc"
    else
        warn "Pomijanie buildu (--skip-build)"
    fi

    push_image "$svc"
    ok "Deploy ${svc} — obraz w registry"
}

show_status() {
    echo ""
    log "Stan kontenerów na NAS:"
    nas_docker "compose -f ${NAS_COMPOSE_FILE} ps" 2>/dev/null || \
        nas_docker "ps --filter name=lenie --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"
}

usage() {
    echo "Usage: $0 [OPTIONS] [service ...]"
    echo ""
echo "Services: frontend, app2, backend, worker, cloud-bridge, document-worker, db, minio, ner-service, obsidian-headless-sync, all (default: core services)"
    echo "  Note: 'all' deploys core services only (db, backend, frontend, app2)."
    echo "  minio, ner-service and obsidian-headless-sync must be deployed explicitly."
    echo ""
    echo "Options:"
    echo "  --skip-build      Skip Docker build, push existing local image"
    echo "  --compose-only    Only run compose up on NAS (no build/push)"
    echo "  --sync-compose    Copy compose.nas.yaml to NAS before deploying"
    echo "  --help, -h        Show this help"
    echo ""
    echo "Examples:"
    echo "  $0                           # Build, push & deploy core services"
    echo "  $0 frontend                  # Build, push & deploy frontend only"
    echo "  $0 minio                     # Deploy MinIO (official image, no build)"
    echo "  $0 obsidian-headless-sync    # Deploy obsidian-headless-sync (official image, no build)"
    echo "  $0 --skip-build backend      # Push existing image & deploy"
    echo "  $0 --compose-only            # Just compose up on NAS"
    echo "  $0 --sync-compose            # Sync compose file and deploy all"
    echo "  $0 --sync-compose frontend   # Sync compose file and deploy frontend"
    exit 0
}

# --- Main ---
SKIP_BUILD="false"
COMPOSE_ONLY="false"
SYNC_COMPOSE="false"
SERVICES=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-build)    SKIP_BUILD="true"; shift ;;
        --compose-only)  COMPOSE_ONLY="true"; shift ;;
        --sync-compose)  SYNC_COMPOSE="true"; shift ;;
        --help|-h)       usage ;;
        all)             SERVICES="$ALL_SERVICES"; shift ;;
        frontend|app2|backend|worker|cloud-bridge|document-worker|db|minio|ner-service|obsidian-headless-sync) SERVICES="$SERVICES $1"; shift ;;
        *) error "Nieznany argument: $1. Użyj --help." ;;
    esac
done

# Default: all services
if [ -z "$SERVICES" ]; then
    SERVICES="$ALL_SERVICES"
fi

echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Lenie NAS Deploy (Registry)${NC}"
echo -e "${GREEN}  NAS: ${NAS_HOST}${NC}"
echo -e "${GREEN}  Registry: ${REGISTRY}${NC}"
echo -e "${GREEN}  Services: ${SERVICES}${NC}"
echo -e "${GREEN}  Skip build: ${SKIP_BUILD}${NC}"
echo -e "${GREEN}  Compose only: ${COMPOSE_ONLY}${NC}"
echo -e "${GREEN}============================================${NC}"

check_nas_connection
sync_site_rules

# Compose must be updated before the migration runner; older Compose files do
# not know the worker/migrate services.
sync_compose

if [ "$COMPOSE_ONLY" = "true" ]; then
    # Only compose up — no build, no push
    deploy_on_nas "$SERVICES"
    show_status
else
    # Full workflow: build → push → deploy
    check_docker_local
    check_registry

    for svc in $SERVICES; do
        deploy_service "$svc" "$SKIP_BUILD"
    done

    log "Uruchamianie migration runnera przed restartem aplikacji..."
    # lenie-migrate shares the backend image (lenie-ai-server:latest); without an
    # explicit pull here it silently runs against whatever was last cached on the
    # NAS docker host, even though a newer image with new migration files was just
    # pushed to the registry above (compose only pulls the *requested* services
    # further down, in deploy_on_nas, which runs AFTER this step).
    nas_docker "compose -f ${NAS_COMPOSE_FILE} pull lenie-migrate"
    nas_docker "compose -f ${NAS_COMPOSE_FILE} run --rm lenie-migrate"
    ok "Migracje zakończone"
    deploy_on_nas "$SERVICES"
    show_status
fi

echo ""
ok "Deploy zakończony!"
echo ""
echo "  Frontend:    http://${NAS_HOST}:3000"
echo "  Admin Panel: http://${NAS_HOST}:3001"
echo "  Backend API: http://${NAS_HOST}:5055"
echo "  PostgreSQL:  ${NAS_HOST}:5434"
echo "  Vault UI:    http://${NAS_HOST}:8210/ui"
echo "  MinIO Console: http://${NAS_HOST}:9001"
echo ""
echo "  Registry:    http://${REGISTRY}/v2/_catalog"
echo ""
