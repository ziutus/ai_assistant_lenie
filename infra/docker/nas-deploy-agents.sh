#!/bin/bash
# Rejestr wdrozen agentow dla nas-deploy.sh (source'owany, nie uruchamiany osobno).
#
# Blokada (.nas-deploy.lock) mowi tylko "ktos wdraza teraz". Rejestr mowi tez kto,
# z jakiego brancha, po co i - co wazniejsze - czy wdrozona zmiana czeka jeszcze na
# test uzytkownika, zanim kolejny agent nadpisze ten sam serwis swoja wersja.
#
# Jeden plik key=value na branch w ${NAS_COMPOSE_DIR}/.nas-agents/<branch>.env.
# Stany: deploying -> deployed (czeka na test) -> done (uzytkownik potwierdzil);
# deploying zamienia sie w failed, gdy skrypt konczy sie bledem.
# Wymaga od hosta: nas_ssh, log/ok/warn/error, NAS_COMPOSE_DIR, NAS_HOST, PROJECT_ROOT.

AGENTS_DIR="${NAS_COMPOSE_DIR}/.nas-agents"
AGENT_ENTRY_TTL_S="${LENIE_AGENT_ENTRY_TTL:-86400}"
AGENT_STATE=""
AGENT_ENTRY_NAME=""
AGENT_BRANCH=""
AGENT_COMMIT=""
AGENT_DIRTY="no"
AGENT_IN_MAIN="no"
AGENT_STARTED=0
AGENT_SERVICES=""
AGENT_TEST_URL=""
AGENT_REASON=""
AGENT_HITS=0

# Wartosci ida do plikow czytanych linia po linii (nigdy source'owanych) i do
# polecen zdalnych, wiec usuwamy znaki sterujace i metaznaki powloki.
agent_clean() {
    printf '%s' "$1" | tr '\r\n\t' '   ' | sed "s/['\"\\\\\$\`|;&<>()]/ /g" | cut -c1-300
}

# backend, worker i cloud-bridge to jeden obraz (lenie-ai-server) - jedna jednostka.
agent_units() {
    local s u out=""
    for s in $1; do
        case "$s" in
            worker|cloud-bridge|backend) u="backend" ;;
            *) u="$s" ;;
        esac
        if [[ " $out " != *" $u "* ]]; then out="$out $u"; fi
    done
    echo "$out"
}

agent_init() {
    local br
    br=$(git -C "$PROJECT_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)
    AGENT_COMMIT=$(git -C "$PROJECT_ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)
    if [ "$br" = "HEAD" ]; then br="detached-${AGENT_COMMIT}"; fi
    AGENT_BRANCH="$br"
    AGENT_ENTRY_NAME=$(printf '%s' "$br" | tr -c 'A-Za-z0-9._-' '_')
    if [ -n "$(git -C "$PROJECT_ROOT" status --porcelain 2>/dev/null | head -1)" ]; then AGENT_DIRTY="yes"; fi
    if git -C "$PROJECT_ROOT" merge-base --is-ancestor HEAD origin/main 2>/dev/null; then AGENT_IN_MAIN="yes"; fi
    AGENT_STARTED=$(date +%s)
}

agent_write_entry() {
    local state="$1"
    AGENT_STATE="$state"
    if [ -z "$AGENT_ENTRY_NAME" ]; then return 0; fi
    {
        printf 'branch=%s\n' "$(agent_clean "$AGENT_BRANCH")"
        printf 'commit=%s\n' "$(agent_clean "$AGENT_COMMIT")"
        printf 'in_main=%s\n' "$AGENT_IN_MAIN"
        printf 'dirty=%s\n' "$AGENT_DIRTY"
        printf 'services=%s\n' "$(agent_clean "$AGENT_SERVICES")"
        printf 'reason=%s\n' "$(agent_clean "${AGENT_REASON:-brak powodu}")"
        printf 'state=%s\n' "$state"
        printf 'started=%s\n' "$AGENT_STARTED"
        printf 'updated=%s\n' "$(date +%s)"
        printf 'test_url=%s\n' "$(agent_clean "$AGENT_TEST_URL")"
        printf 'host=%s\n' "$(agent_clean "$(hostname)")"
        printf 'user=%s\n' "$(agent_clean "${USER:-${USERNAME:-unknown}}")"
    } | nas_ssh "mkdir -p '${AGENTS_DIR}' && cat > '${AGENTS_DIR}/${AGENT_ENTRY_NAME}.env'" \
        || warn "Nie udalo sie zapisac wpisu rejestru wdrozen (${AGENTS_DIR}) - deploy trwa dalej"
}

# Zmiana samego stanu cudzego/wlasnego wpisu (np. user potwierdzil test -> done).
agent_mark_done() {
    local name="$1" body
    if [[ ! "$name" =~ ^[A-Za-z0-9._-]+$ ]]; then error "Niepoprawna nazwa wpisu: '${name}'"; fi
    body=$(nas_ssh "cat '${AGENTS_DIR}/${name}.env' 2>/dev/null" || true)
    if [ -z "$body" ]; then error "Brak wpisu '${name}' w ${AGENTS_DIR} (--list-deploys pokazuje wpisy)."; fi
    printf '%s\n' "$body" | grep -v '^state=' | grep -v '^updated=' \
        | { cat; printf 'state=done\nupdated=%s\n' "$(date +%s)"; } \
        | nas_ssh "cat > '${AGENTS_DIR}/${name}.env'"
    ok "Wpis '${name}' oznaczony jako done (test potwierdzony)"
}

agent_entries() {
    nas_ssh "for f in '${AGENTS_DIR}'/*.env; do [ -f \"\$f\" ] || continue; echo \"@@\$(basename \"\$f\" .env)\"; cat \"\$f\"; done" 2>/dev/null || true
}

agent_entry_reset() {
    E_BRANCH=""; E_COMMIT=""; E_INMAIN=""; E_DIRTY=""; E_SERVICES=""; E_REASON=""
    E_STATE=""; E_UPDATED=0; E_TEST=""; E_HOST=""; E_USER=""
}

# Drukuje biezacy wpis (E_*), jesli pasuje do trybu: list (wszystkie), busy (trwajace
# wdrozenia), conflict (cudze, swieze, deploying/deployed, ten sam serwis co nasz).
agent_entry_flush() {
    local mode="$1" age unit mine overlap="" note=""
    if [ -z "${E_NAME:-}" ]; then return 0; fi
    age=$(( $(date +%s) - ${E_UPDATED:-0} ))
    case "$mode" in
        list) ;;
        busy)
            if [ "$E_STATE" != "deploying" ]; then return 0; fi
            ;;
        conflict)
            if [ "$E_NAME" = "$AGENT_ENTRY_NAME" ]; then return 0; fi
            if [ "$E_STATE" != "deploying" ] && [ "$E_STATE" != "deployed" ]; then return 0; fi
            if [ "$age" -gt "$AGENT_ENTRY_TTL_S" ]; then return 0; fi
            mine=" $(agent_units "$AGENT_SERVICES") "
            for unit in $(agent_units "$E_SERVICES"); do
                if [[ "$mine" == *" $unit "* ]]; then overlap="$overlap $unit"; fi
            done
            if [ -z "$overlap" ]; then return 0; fi
            ;;
    esac
    AGENT_HITS=$((AGENT_HITS + 1))
    if [ "$E_STATE" = "deployed" ]; then note=", czeka na test uzytkownika${E_TEST:+: $E_TEST}"; fi
    if [ "$E_INMAIN" = "no" ]; then note="$note, branch NIE w main"; fi
    if [ "$E_DIRTY" = "yes" ]; then note="$note, niezatwierdzone zmiany"; fi
    echo "  - ${E_BRANCH:-$E_NAME} @ ${E_COMMIT:-?} [${E_STATE:-?}, $(( age / 60 )) min temu${note}]"
    echo "      serwisy:${E_SERVICES:+ $E_SERVICES}   (${E_USER:-?}@${E_HOST:-?}, wpis '${E_NAME}')"
    echo "      powod: ${E_REASON:-brak}"
}

agent_scan() {
    local mode="$1" line
    AGENT_HITS=0
    E_NAME=""
    agent_entry_reset
    while IFS= read -r line; do
        line="${line%$'\r'}"
        case "$line" in
            @@*) agent_entry_flush "$mode"; agent_entry_reset; E_NAME="${line#@@}" ;;
            branch=*)   E_BRANCH="${line#branch=}" ;;
            commit=*)   E_COMMIT="${line#commit=}" ;;
            in_main=*)  E_INMAIN="${line#in_main=}" ;;
            dirty=*)    E_DIRTY="${line#dirty=}" ;;
            services=*) E_SERVICES="${line#services=}" ;;
            reason=*)   E_REASON="${line#reason=}" ;;
            state=*)    E_STATE="${line#state=}" ;;
            updated=*)  E_UPDATED="${line#updated=}" ;;
            test_url=*) E_TEST="${line#test_url=}" ;;
            host=*)     E_HOST="${line#host=}" ;;
            user=*)     E_USER="${line#user=}" ;;
        esac
    done < <(agent_entries)
    agent_entry_flush "$mode"
}
