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
NAS_DOCKER="/share/CACHEDEV1_DATA/.qpkg/container-station/usr/bin/.libs/docker"
NAS_COMPOSE_DIR="/share/Container/lenie-compose"
NAS_COMPOSE_FILE="${NAS_COMPOSE_DIR}/compose.nas.yaml"
REGISTRY="${NAS_HOST}:5005"

# Project root (two levels up from this script)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOCAL_COMPOSE_FILE="${SCRIPT_DIR}/compose.nas.yaml"

# Service definitions: name | local image | registry image | dockerfile
declare -A SVC_IMAGE=(
    [frontend]="lenie-ai-frontend:latest"
    [app2]="lenie-ai-app2:latest"
    [backend]="lenie-ai-server:latest"
    [db]="lenie-ai-db:latest"
)
declare -A SVC_REGISTRY_IMAGE=(
    [frontend]="${REGISTRY}/lenie-ai-frontend:latest"
    [app2]="${REGISTRY}/lenie-ai-app2:latest"
    [backend]="${REGISTRY}/lenie-ai-server:latest"
    [db]="${REGISTRY}/lenie-ai-db:latest"
)
declare -A SVC_DOCKERFILE=(
    [frontend]="web_interface_react/Dockerfile"
    [app2]="web_interface_app2/Dockerfile"
    [backend]="backend/Dockerfile"
    [db]="infra/docker/Postgresql/Dockerfile"
)
declare -A SVC_COMPOSE_NAME=(
    [frontend]="lenie-ai-frontend"
    [app2]="lenie-ai-app2"
    [backend]="lenie-ai-server"
    [db]="lenie-ai-db"
)

ALL_SERVICES="db backend frontend app2"

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
    docker build -t "$image" -f "$dockerfile" . 2>&1 | tail -5
    ok "Obraz ${image} zbudowany"
}

push_image() {
    local svc="$1"
    local image="${SVC_IMAGE[$svc]}"
    local registry_image="${SVC_REGISTRY_IMAGE[$svc]}"

    log "Tagowanie ${image} → ${registry_image}..."
    docker tag "$image" "$registry_image"

    log "Pushowanie do registry: ${registry_image}..."
    docker push "$registry_image"
    ok "Obraz ${registry_image} w registry"
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

deploy_service() {
    local svc="$1"
    local skip_build="$2"

    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}  Deploying: ${svc}${NC}"
    echo -e "${BLUE}========================================${NC}"

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
    echo "Services: frontend, app2, backend, db, all (default)"
    echo ""
    echo "Options:"
    echo "  --skip-build      Skip Docker build, push existing local image"
    echo "  --compose-only    Only run compose up on NAS (no build/push)"
    echo "  --sync-compose    Copy compose.nas.yaml to NAS before deploying"
    echo "  --help, -h        Show this help"
    echo ""
    echo "Examples:"
    echo "  $0                           # Build, push & deploy all"
    echo "  $0 frontend                  # Build, push & deploy frontend only"
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
        frontend|app2|backend|db) SERVICES="$SERVICES $1"; shift ;;
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

# Sync compose file if requested
if [ "$SYNC_COMPOSE" = "true" ]; then
    sync_compose
fi

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
echo ""
echo "  Registry:    http://${REGISTRY}/v2/_catalog"
echo ""
