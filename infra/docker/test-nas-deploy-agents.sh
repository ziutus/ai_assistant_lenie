#!/bin/bash
# Lokalny test rejestru wdrozen (nas-deploy-agents.sh) - bez NAS: nas_ssh wykonuje
# polecenia na katalogu tymczasowym. Uruchomienie: bash infra/docker/test-nas-deploy-agents.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TMP_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMP_ROOT"' EXIT

NAS_COMPOSE_DIR="$TMP_ROOT/lenie-compose"
NAS_HOST="test-nas"
mkdir -p "$NAS_COMPOSE_DIR"
nas_ssh() { bash -c "$1"; }
log() { :; }
ok() { echo "ok: $*"; }
warn() { echo "warn: $*"; }
error() { echo "error: $*"; exit 1; }

# shellcheck source=nas-deploy-agents.sh
source "$SCRIPT_DIR/nas-deploy-agents.sh"

fails=0
check() { # opis, warunek (0 = ok)
    if [ "$2" -eq 0 ]; then echo "PASS $1"; else echo "FAIL $1"; fails=$((fails + 1)); fi
}

# 1) Agent A wdraza backend: wpis powstaje, tekst powodu jest oczyszczony.
agent_init
AGENT_BRANCH="agent-a"; AGENT_ENTRY_NAME="agent-a"
AGENT_SERVICES="backend worker cloud-bridge"
AGENT_REASON="fix; \$(rm -rf /) 'quote' |pipe"
AGENT_TEST_URL="http://test-nas:5055"
agent_write_entry deployed
test -f "$AGENTS_DIR/agent-a.env"; check "wpis A zapisany" $?
! grep -q '[;$|]' "$AGENTS_DIR/agent-a.env"; check "powod bez metaznakow" $?

# 2) Agent B wdraza frontend: brak konfliktu (inna jednostka).
AGENT_BRANCH="agent-b"; AGENT_ENTRY_NAME="agent-b"; AGENT_SERVICES="frontend"
agent_scan conflict
[ "$AGENT_HITS" -eq 0 ]; check "frontend nie koliduje z backend" $?

# 3) Agent B wdraza tez worker -> ta sama jednostka co backend -> konflikt, z powodem.
AGENT_SERVICES="worker"
out=$(agent_scan conflict; echo "hits=$AGENT_HITS")
[[ "$out" == *"agent-a"* && "$out" == *"czeka na test"* && "$out" == *"powod:"* ]]; check "konflikt pokazuje kto, stan i powod" $?
agent_scan conflict
[ "$AGENT_HITS" -eq 1 ]; check "dokladnie jeden konflikt" $?

# 4) Wlasny wpis nie jest konfliktem.
AGENT_BRANCH="agent-a"; AGENT_ENTRY_NAME="agent-a"; AGENT_SERVICES="backend"
agent_scan conflict
[ "$AGENT_HITS" -eq 0 ]; check "wlasny wpis ignorowany" $?

# 5) Po --mark-done wpis A nie koliduje.
agent_mark_done "agent-a" >/dev/null
AGENT_BRANCH="agent-b"; AGENT_ENTRY_NAME="agent-b"; AGENT_SERVICES="backend"
agent_scan conflict
[ "$AGENT_HITS" -eq 0 ]; check "done nie koliduje" $?
grep -q '^state=done$' "$AGENTS_DIR/agent-a.env"; check "stan done zapisany" $?

# 6) Stary wpis (po TTL) nie koliduje.
AGENT_BRANCH="agent-a"; AGENT_ENTRY_NAME="agent-a"; AGENT_SERVICES="backend"; AGENT_REASON="stary"
agent_write_entry deployed
sed -i "s/^updated=.*/updated=1/" "$AGENTS_DIR/agent-a.env"
AGENT_BRANCH="agent-b"; AGENT_ENTRY_NAME="agent-b"
agent_scan conflict
[ "$AGENT_HITS" -eq 0 ]; check "wpis po TTL ignorowany" $?

# 7) busy pokazuje tylko deploying.
AGENT_BRANCH="agent-a"; AGENT_ENTRY_NAME="agent-a"; agent_write_entry deploying
agent_scan busy
[ "$AGENT_HITS" -eq 1 ]; check "busy widzi deploying" $?
agent_write_entry failed
agent_scan busy
[ "$AGENT_HITS" -eq 0 ]; check "busy nie widzi failed" $?

# 8) mark-done na nieistniejacym wpisie konczy sie bledem.
if ( agent_mark_done "nie-ma" ) >/dev/null 2>&1; then rc=0; else rc=1; fi
[ "$rc" -ne 0 ]; check "mark-done nieistniejacego wpisu = blad" $?

if [ "$fails" -ne 0 ]; then echo "$fails testow nie przeszlo"; exit 1; fi
echo "Wszystkie testy rejestru przeszly"
