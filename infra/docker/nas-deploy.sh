#!/bin/bash
set -euo pipefail

# ============================================================================
# NAS Deploy Script - Build, transfer and deploy Docker images to QNAP NAS
# Usage:
#   ./nas-deploy.sh              # Deploy all services
#   ./nas-deploy.sh frontend     # Deploy only frontend (web_interface_react)
#   ./nas-deploy.sh app2         # Deploy only admin panel (web_interface_app2)
#   ./nas-deploy.sh backend      # Deploy only backend (Flask server)
#   ./nas-deploy.sh db           # Deploy only database (PostgreSQL + pgvector)
#   ./nas-deploy.sh --skip-build frontend  # Transfer and restart without rebuilding
# ============================================================================

# --- Configuration ---
NAS_HOST="192.168.200.7"
NAS_USER="admin"
NAS_DOCKER="/share/CACHEDEV1_DATA/.qpkg/container-station/usr/bin/.libs/docker"
NAS_CONTAINER_DIR="/share/Container"
NAS_ENV_FILE="/share/Container/lenie-env/.env"
NAS_NETWORK="lenie-net"

# Project root (two levels up from this script)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Service definitions: name | image | dockerfile (relative to PROJECT_ROOT) | port_mapping | extra_args
declare -A SVC_IMAGE=(
    [frontend]="lenie-ai-frontend:latest"
    [app2]="lenie-ai-app2:latest"
    [backend]="lenie-ai-server:latest"
    [db]="lenie-ai-db:latest"
)
declare -A SVC_DOCKERFILE=(
    [frontend]="web_interface_react/Dockerfile"
    [app2]="web_interface_app2/Dockerfile"
    [backend]="backend/Dockerfile"
    [db]="infra/docker/Postgresql/Dockerfile"
)
declare -A SVC_CONTAINER=(
    [frontend]="lenie-ai-frontend"
    [app2]="lenie-ai-app2"
    [backend]="lenie-ai-server"
    [db]="lenie-ai-db"
)
declare -A SVC_PORTS=(
    [frontend]="3000:80"
    [app2]="3001:80"
    [backend]="5055:5000"
    [db]="5434:5432"
)
declare -A SVC_EXTRA=(
    [frontend]=""
    [app2]=""
    [backend]="--network ${NAS_NETWORK} --env-file ${NAS_ENV_FILE} -v lenie-ai-data:/app/data"
    [db]="-e POSTGRES_PASSWORD=postgres -v lenie-ai-db-data:/var/lib/postgresql/data"
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

build_image() {
    local svc="$1"
    local image="${SVC_IMAGE[$svc]}"
    local dockerfile="${SVC_DOCKERFILE[$svc]}"

    log "Budowanie obrazu: ${image} (${dockerfile})..."
    cd "$PROJECT_ROOT"
    docker build -t "$image" -f "$dockerfile" . 2>&1 | tail -5
    ok "Obraz ${image} zbudowany"
}

transfer_image() {
    local svc="$1"
    local image="${SVC_IMAGE[$svc]}"
    local archive="/tmp/lenie-${svc}.tar.gz"

    log "Eksportowanie obrazu ${image}..."
    docker save "$image" | gzip > "$archive"
    local size
    size=$(du -h "$archive" | cut -f1)
    ok "Obraz wyeksportowany (${size})"

    log "Przesyłanie na NAS..."
    scp "$archive" "${NAS_USER}@${NAS_HOST}:${NAS_CONTAINER_DIR}/"
    ok "Przesłano na NAS"

    log "Ładowanie obrazu na NAS..."
    nas_docker "load -i ${NAS_CONTAINER_DIR}/lenie-${svc}.tar.gz"
    ok "Obraz załadowany na NAS"

    # Cleanup
    rm -f "$archive"
    nas_ssh "rm -f ${NAS_CONTAINER_DIR}/lenie-${svc}.tar.gz"
}

restart_container() {
    local svc="$1"
    local container="${SVC_CONTAINER[$svc]}"
    local image="${SVC_IMAGE[$svc]}"
    local ports="${SVC_PORTS[$svc]}"
    local extra="${SVC_EXTRA[$svc]}"

    log "Restartowanie kontenera ${container}..."

    # Stop and remove old container (ignore errors if not exists)
    nas_docker "stop ${container}" 2>/dev/null || true
    nas_docker "rm ${container}" 2>/dev/null || true

    # Start new container
    nas_docker "run -d --name ${container} --restart unless-stopped -p ${ports} ${extra} ${image}"
    ok "Kontener ${container} uruchomiony (port ${ports})"
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

    transfer_image "$svc"
    restart_container "$svc"

    ok "Deploy ${svc} zakończony!"
}

ensure_nas_network() {
    log "Sprawdzanie sieci Docker na NAS..."
    if ! nas_docker "network inspect ${NAS_NETWORK}" &>/dev/null; then
        log "Tworzenie sieci ${NAS_NETWORK}..."
        nas_docker "network create ${NAS_NETWORK}"
    fi

    # Ensure DB is connected to the network
    nas_docker "network connect ${NAS_NETWORK} lenie-ai-db" 2>/dev/null || true
    ok "Sieć ${NAS_NETWORK} OK"
}

show_status() {
    echo ""
    log "Stan kontenerów na NAS:"
    nas_docker "ps --filter name=lenie-ai --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"
}

usage() {
    echo "Usage: $0 [--skip-build] [service|all]"
    echo ""
    echo "Services: frontend, app2, backend, db, all (default)"
    echo ""
    echo "Options:"
    echo "  --skip-build    Skip Docker build, only transfer and restart"
    echo ""
    echo "Examples:"
    echo "  $0                    # Build and deploy all services"
    echo "  $0 frontend           # Build and deploy frontend only"
    echo "  $0 --skip-build app2  # Transfer and restart app2 without rebuilding"
    exit 0
}

# --- Main ---
SKIP_BUILD="false"
SERVICES=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-build) SKIP_BUILD="true"; shift ;;
        --help|-h)    usage ;;
        all)          SERVICES="$ALL_SERVICES"; shift ;;
        frontend|app2|backend|db) SERVICES="$SERVICES $1"; shift ;;
        *) error "Nieznany argument: $1. Użyj --help." ;;
    esac
done

# Default: all services
if [ -z "$SERVICES" ]; then
    SERVICES="$ALL_SERVICES"
fi

echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Lenie NAS Deploy${NC}"
echo -e "${GREEN}  NAS: ${NAS_HOST}${NC}"
echo -e "${GREEN}  Services: ${SERVICES}${NC}"
echo -e "${GREEN}  Skip build: ${SKIP_BUILD}${NC}"
echo -e "${GREEN}============================================${NC}"

check_docker_local
check_nas_connection

# Ensure network exists if deploying backend
if [[ "$SERVICES" == *"backend"* ]]; then
    ensure_nas_network
fi

for svc in $SERVICES; do
    deploy_service "$svc" "$SKIP_BUILD"
done

show_status

echo ""
ok "Deploy zakończony!"
echo ""
echo "  Frontend:    http://${NAS_HOST}:3000"
echo "  Admin Panel: http://${NAS_HOST}:3001"
echo "  Backend API: http://${NAS_HOST}:5055"
echo "  PostgreSQL:  ${NAS_HOST}:5434"
echo ""
