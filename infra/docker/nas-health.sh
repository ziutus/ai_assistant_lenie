#!/bin/bash
# ============================================================================
# nas-health.sh - Snapshot stanu NAS-a (QNAP) i stacka Lenie
#
# Jedno uruchomienie zbiera to, czego zwykle szuka sie recznie przy awarii:
#   - osiagalnosc sieciowa (ping) + endpointy HTTP (backend/frontend/admin/
#     vault/minio/registry) z czasami odpowiedzi
#   - przez SSH: uptime, load vs. liczba rdzeni, pamiec + swap, zajetosc dyskow
#   - slady OOM-killera / panic / hung task w dmesg biezacego bootu
#   - snapshot hosta (busybox top): CPU idle%, procesy wg zajetosci pamieci
#   - stan kontenerow lenie: status, health, RestartCount, OOMKilled
#   - docker stats (CPU / RAM per kontener)
#
# Kod wyjscia: 0 = OK, 1 = ostrzezenia, 2 = stan krytyczny / NAS nieosiagalny
#
# Uzycie:
#   ./nas-health.sh              # pelny raport (HTTP + SSH)
#   ./nas-health.sh --no-ssh     # tylko sondy sieciowe (gdy brak klucza SSH)
#   ./nas-health.sh --logs       # dodatkowo ostatnie linie logu backendu
#   ./nas-health.sh --json       # zwiezle podsumowanie w JSON na koncu
#
# Zmienne srodowiskowe:
#   NAS_HOST (domyslnie 192.168.200.7), NAS_USER (admin)
#   LENIE_API_KEY - jesli ustawiony, dochodzi keyed test /whoami (backend + DB)
# ============================================================================
set -uo pipefail

# --- Konfiguracja (spojna z nas-deploy.sh) ---
NAS_HOST="${NAS_HOST:-192.168.200.7}"
NAS_USER="${NAS_USER:-admin}"
NAS_DOCKER="/share/CACHEDEV4_DATA/.qpkg/container-station/bin/docker"
NAS_COMPOSE_FILE="/share/ContainerNew/lenie-compose/compose.nas.yaml"
HTTP_TIMEOUT=10
SLOW_HTTP_S=2.0          # powyzej tego czasu odpowiedzi HTTP -> WARN

# Progi (load liczony wzgledem liczby rdzeni CPU)
LOAD_WARN_FACTOR=0.9
LOAD_CRIT_FACTOR=1.5
MEM_WARN_PCT=85
MEM_CRIT_PCT=95
SWAP_WARN_MB=256
DISK_WARN_PCT=85
DISK_CRIT_PCT=95

# --- Flagi ---
DO_SSH=true
DO_LOGS=false
DO_JSON=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-ssh)  DO_SSH=false; shift ;;
        --logs)    DO_LOGS=true; shift ;;
        --json)    DO_JSON=true; shift ;;
        --help|-h)
            awk '/^#!/{next} /^#/{sub(/^# ?/,"");print;next} {exit}' "$0"
            exit 0 ;;
        *) echo "Nieznany argument: $1 (uzyj --help)" >&2; exit 64 ;;
    esac
done

# --- Kolory (wylaczone gdy stdout nie jest terminalem albo NO_COLOR) ---
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; DIM='\033[2m'; NC='\033[0m'
else
    RED=''; GREEN=''; YELLOW=''; BLUE=''; DIM=''; NC=''
fi

WARN_COUNT=0
CRIT_COUNT=0
declare -a NOTES=()

ok()   { echo -e "  ${GREEN}[ OK ]${NC} $*"; }
warn() { echo -e "  ${YELLOW}[WARN]${NC} $*"; WARN_COUNT=$((WARN_COUNT + 1)); NOTES+=("WARN: $*"); }
crit() { echo -e "  ${RED}[CRIT]${NC} $*"; CRIT_COUNT=$((CRIT_COUNT + 1)); NOTES+=("CRIT: $*"); }
info() { echo -e "  ${DIM}$*${NC}"; }
hdr()  { echo -e "\n${BLUE}== $* ==${NC}"; }

# awk-owe porownanie liczb zmiennoprzecinkowych: gt A B -> exit 0 gdy A > B
gt() { awk -v a="$1" -v b="$2" 'BEGIN{ exit !(a+0 > b+0) }'; }

nas_ssh() { ssh -o ConnectTimeout=8 -o BatchMode=yes "${NAS_USER}@${NAS_HOST}" "$@"; }

# http_probe NAZWA URL [oczekiwany_kod]  (0 lub "2xx/3xx" akceptowane gdy pominiete)
http_probe() {
    local name="$1" url="$2" expect="${3:-}"
    local out code t
    out=$(curl -s -m "$HTTP_TIMEOUT" -o /dev/null -w '%{http_code} %{time_total}' "$url" 2>/dev/null) || out="000 0"
    code="${out% *}"; t="${out#* }"
    if [ "$code" = "000" ]; then
        crit "${name}: brak odpowiedzi (timeout ${HTTP_TIMEOUT}s) - ${url}"
        return 1
    fi
    if [ -n "$expect" ] && [ "$code" != "$expect" ]; then
        warn "${name}: HTTP ${code} (oczekiwano ${expect}) w ${t}s - ${url}"
        return 1
    fi
    if [ -z "$expect" ] && ! [[ "$code" =~ ^[23] ]]; then
        warn "${name}: HTTP ${code} w ${t}s - ${url}"
        return 1
    fi
    if gt "$t" "$SLOW_HTTP_S"; then
        warn "${name}: HTTP ${code} ale wolno (${t}s) - mozliwe obciazenie"
    else
        ok "${name}: HTTP ${code} (${t}s)"
    fi
    return 0
}

echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Lenie NAS Health  -  ${NAS_HOST}${NC}"
echo -e "${GREEN}  $(date '+%Y-%m-%d %H:%M:%S %z')${NC}"
echo -e "${GREEN}============================================${NC}"

# ---------------------------------------------------------------------------
hdr "Siec"
# ---------------------------------------------------------------------------
PING_OUT=$(ping -n 3 -w 3000 "$NAS_HOST" 2>/dev/null || ping -c 3 -W 3 "$NAS_HOST" 2>/dev/null || true)
if echo "$PING_OUT" | grep -qiE 'ttl=|bytes from'; then
    RTT=$(echo "$PING_OUT" | grep -oiE 'time[=<][0-9.]+ *ms' | grep -oE '[0-9.]+' | tail -1)
    ok "ping ${NAS_HOST} odpowiada${RTT:+ (~${RTT} ms)}"
else
    crit "ping ${NAS_HOST} - BRAK odpowiedzi (warstwa sieciowa)"
    if echo "$PING_OUT" | grep -qi 'unreachable'; then
        info "\"Destination host unreachable\" + brak ARP = NAS wylaczony lub twardy zwis."
        info "Sprawdz gateway: ping 192.168.200.1  (jesli dziala -> problem po stronie NAS-a)"
        info "Konieczna fizyczna interwencja: diody NAS-a, ewentualnie twardy restart."
    fi
    echo
    echo -e "${RED}NAS nieosiagalny w sieci - dalsze testy pominiete.${NC}"
    [ "$DO_JSON" = true ] && echo '{"reachable":false,"warn":0,"crit":1}'
    exit 2
fi

# ---------------------------------------------------------------------------
hdr "Endpointy HTTP"
# ---------------------------------------------------------------------------
http_probe "backend /healthz" "http://${NAS_HOST}:5055/healthz" 200
BACKEND_VER=$(curl -s -m "$HTTP_TIMEOUT" "http://${NAS_HOST}:5055/version" 2>/dev/null \
    | grep -oE '"app_version"[^,]*' | grep -oE '[0-9]+(\.[0-9]+)+' | head -1)
[ -n "$BACKEND_VER" ] && info "wersja backendu: ${BACKEND_VER}"
http_probe "frontend :3000" "http://${NAS_HOST}:3000/"
http_probe "admin :3001"    "http://${NAS_HOST}:3001/"
http_probe "MinIO :9000"    "http://${NAS_HOST}:9000/minio/health/live"
http_probe "registry :5005" "http://${NAS_HOST}:5005/v2/"

# Vault - rozroznienie sealed/unsealed
VAULT_JSON=$(curl -s -m "$HTTP_TIMEOUT" "http://${NAS_HOST}:8210/v1/sys/health" 2>/dev/null || true)
if [ -z "$VAULT_JSON" ]; then
    crit "Vault :8210 - brak odpowiedzi"
elif echo "$VAULT_JSON" | grep -q '"sealed":false'; then
    ok "Vault :8210 - odpieczetowany (unsealed)"
else
    crit "Vault :8210 - ZAPIECZETOWANY (sealed) - backend nie wczyta sekretow"
fi

# PostgreSQL - test TCP
if (exec 3<>"/dev/tcp/${NAS_HOST}/5434") 2>/dev/null; then
    exec 3>&- 3<&-
    ok "PostgreSQL :5434 - port otwarty"
else
    crit "PostgreSQL :5434 - port nieosiagalny"
fi

# Keyed test: backend + DB + auth (opcjonalny)
if [ -n "${LENIE_API_KEY:-}" ]; then
    WHOAMI=$(curl -s -m "$HTTP_TIMEOUT" -w ' [%{http_code}]' \
        -H "x-api-key: ${LENIE_API_KEY}" "http://${NAS_HOST}:5055/whoami" 2>/dev/null || true)
    if echo "$WHOAMI" | grep -q '\[200\]'; then
        ok "keyed /whoami - backend+DB+auth dzialaja end-to-end"
    else
        warn "keyed /whoami - nieoczekiwana odpowiedz:${WHOAMI:0:120}"
    fi
else
    info "LENIE_API_KEY nieustawiony - pominieto keyed test /whoami"
fi

if [ "$DO_SSH" = false ]; then
    echo -e "\n${DIM}--no-ssh: pominieto diagnostyke systemowa.${NC}"
else
# ---------------------------------------------------------------------------
hdr "System (SSH)"
# ---------------------------------------------------------------------------
if ! nas_ssh 'echo ok' >/dev/null 2>&1; then
    warn "SSH ${NAS_USER}@${NAS_HOST} nie dziala - pomijam diagnostyke systemowa (sprawdz klucz)"
else
    OS=$(nas_ssh '
        echo "===UPTIME_S===";  cat /proc/uptime
        echo "===LOADAVG===";   cat /proc/loadavg
        echo "===NCPU===";      grep -c ^processor /proc/cpuinfo
        echo "===MEMINFO===";   grep -E "^(MemTotal|MemAvailable|MemFree|SwapTotal|SwapFree):" /proc/meminfo
        echo "===DISK===";      df -h /share/CACHEDEV*_DATA 2>/dev/null
        echo "===DMESG===";     dmesg 2>/dev/null | grep -iE "out of memory|oom-kill|killed process|kernel panic|hung task|blocked for more than|general protection fault" | tail -15
        echo "===TOP===";       top -bn1 2>/dev/null | head -18
        echo "===HOSTHEALTH==="; cat /share/ContainerNew/lenie-host-health/host-health.json 2>/dev/null
    ' 2>/dev/null)

    sect() { awk -v s="===$1===" 'f && /^===[A-Z_]+===$/{exit} $0==s{f=1;next} f' <<<"$OS"; }

    UP_S=$(sect UPTIME_S | awk '{print int($1)}'); UP_S="${UP_S:-0}"
    NCPU=$(sect NCPU | tr -dc '0-9'); NCPU="${NCPU:-0}"
    read -r L1 L5 L15 _ < <(sect LOADAVG)
    UP_H=$(awk -v s="$UP_S" 'BEGIN{d=int(s/86400);h=int(s%86400/3600);m=int(s%3600/60);
        if(d)printf "%dd %dh",d,h; else if(h)printf "%dh %dm",h,m; else printf "%dm",m}')
    echo -e "  uptime: ${UP_H}   load: ${L1:-?} / ${L5:-?} / ${L15:-?}   (rdzenie: ${NCPU:-?})"

    if [ "${NCPU:-0}" -ge 1 ] && [ -n "${L1:-}" ]; then
        LOAD_WARN=$(awk -v n="$NCPU" -v f="$LOAD_WARN_FACTOR" 'BEGIN{printf "%.2f", n*f}')
        LOAD_CRIT=$(awk -v n="$NCPU" -v f="$LOAD_CRIT_FACTOR" 'BEGIN{printf "%.2f", n*f}')
        LOAD_PCT=$(awk -v a="$L1" -v n="$NCPU" 'BEGIN{printf "%d", a/n*100}')
        if gt "$L1" "$LOAD_CRIT"; then
            crit "load ${L1} = ${LOAD_PCT}% CPU (prog ${LOAD_CRIT} = ${LOAD_CRIT_FACTOR}x rdzenie) - NAS mocno przeciazony"
        elif gt "$L1" "$LOAD_WARN"; then
            warn "load ${L1} = ${LOAD_PCT}% CPU (prog ${LOAD_WARN}) - podwyzszone obciazenie"
        else
            ok "load ${L1} = ${LOAD_PCT}% CPU (${NCPU} rdzenie) - w normie"
        fi
    else
        info "load ${L1:-?} / ${L5:-?} / ${L15:-?} (nie ustalono liczby rdzeni - brak werdyktu)"
    fi

    # Niedawny restart (< 20 min) => sprawdz przyczyne poprzedniego zejscia
    if [ "$UP_S" -gt 0 ] && [ "$UP_S" -lt 1200 ]; then
        warn "NAS wystartowal ${UP_H} temu - sprawdz przyczyne poprzedniego zejscia w QTS > System Logs"
    fi

    # --- Pamiec (z /proc/meminfo, w kB) ---
    mi() { sect MEMINFO | awk -v k="$1:" '$1==k{print $2}'; }
    MT=$(mi MemTotal); MA=$(mi MemAvailable); ST=$(mi SwapTotal); SF=$(mi SwapFree)
    if [ -n "${MT:-}" ] && [ "${MT:-0}" -gt 0 ]; then
        MA="${MA:-$(mi MemFree)}"
        MEM_USED_MB=$(( (MT - MA) / 1024 )); MEM_TOTAL_MB=$(( MT / 1024 ))
        MEM_PCT=$(( (MT - MA) * 100 / MT ))
        if [ "$MEM_PCT" -ge "$MEM_CRIT_PCT" ]; then
            crit "RAM: ${MEM_USED_MB}/${MEM_TOTAL_MB} MB (${MEM_PCT}%) - grozi OOM"
        elif [ "$MEM_PCT" -ge "$MEM_WARN_PCT" ]; then
            warn "RAM: ${MEM_USED_MB}/${MEM_TOTAL_MB} MB (${MEM_PCT}%)"
        else
            ok "RAM: ${MEM_USED_MB}/${MEM_TOTAL_MB} MB (${MEM_PCT}%)"
        fi
    fi
    if [ -n "${ST:-}" ] && [ "${ST:-0}" -gt 0 ]; then
        SWAP_USED_MB=$(( (ST - ${SF:-$ST}) / 1024 ))
        if [ "$SWAP_USED_MB" -ge "$SWAP_WARN_MB" ]; then
            warn "swap w uzyciu: ${SWAP_USED_MB} MB - system pod presja pamieciowa (typowe tuz przed zwisem)"
        else
            ok "swap w uzyciu: ${SWAP_USED_MB} MB"
        fi
    fi

    # --- Dysk ---
    while read -r fs size used avail pct mnt; do
        [ -z "${pct:-}" ] && continue
        [[ "$pct" == *%* ]] || continue
        p="${pct%\%}"
        if [ "$p" -ge "$DISK_CRIT_PCT" ]; then
            crit "dysk ${mnt}: ${pct} zajete (${avail} wolne)"
        elif [ "$p" -ge "$DISK_WARN_PCT" ]; then
            warn "dysk ${mnt}: ${pct} zajete (${avail} wolne)"
        else
            ok "dysk ${mnt}: ${pct} zajete (${avail} wolne)"
        fi
    done < <(sect DISK | tail -n +2)

    # --- dmesg: OOM / panic ---
    DMESG=$(sect DMESG)
    if [ -n "$DMESG" ]; then
        crit "dmesg biezacego bootu zawiera slady OOM/panic/hung task:"
        echo "$DMESG" | sed 's/^/      /'
    else
        ok "dmesg: brak OOM/panic/hung task w biezacym boocie"
        info "(bufor jadra czysci sie przy restarcie - zdarzenia sprzed reboota tylko w QTS > System Logs)"
    fi

    # --- Snapshot admission-gate'u (host-health.json, zbierany co minute cronem) ---
    HH=$(sect HOSTHEALTH)
    if [ -z "$HH" ]; then
        info "host-health.json brak - collector nie wdrozony albo sciezka sie zmienila (patrz docs/deployment/nas/host-health-collector.md)"
    else
        hv() { grep -oE "\"$1\":[^,}]*" <<<"$HH" | head -1 | sed 's/^[^:]*://; s/"//g'; }
        HH_AT=$(hv collected_at); HH_IO=$(hv iowait_percent)
        HH_MEM=$(hv mem_available_bytes); HH_SWAP=$(hv swap_used_bytes)
        HH_TEMPS=$(grep -oE '"disk_temperatures_c":\[[^]]*\]' <<<"$HH" | grep -oE '[0-9]+' | sort -rn | head -1)
        HH_TS=$(date -d "$HH_AT" +%s 2>/dev/null || true)
        HH_AGE=$([ -n "$HH_TS" ] && echo $(( $(date -u +%s) - HH_TS )) || echo -1)
        if [ "$HH_AGE" -lt 0 ]; then
            info "host-health.json: nie sparsowano znacznika czasu (${HH_AT})"
        elif [ "$HH_AGE" -gt 120 ]; then
            warn "host-health.json sprzed ${HH_AGE}s (>120s) - collector/cron na QNAP prawdopodobnie nie dziala; admission gate defensywnie wstrzymuje workery"
        else
            ok "host-health.json swiezy (${HH_AGE}s temu)"
        fi
        # iowait > 15% = sygnatura zajechanego dysku (backup QNAP, reindeks multimediow)
        if [ -n "${HH_IO:-}" ] && gt "$HH_IO" 15; then
            warn "iowait ${HH_IO}% (>15%) - dysk przeciazony (backup / reindeks?); typowa przyczyna spowolnienia calego NAS-a"
        elif [ -n "${HH_IO:-}" ]; then
            ok "iowait ${HH_IO}%"
        fi
        if [ -n "${HH_MEM:-}" ]; then
            HH_MEM_MB=$(( HH_MEM / 1048576 ))
            [ "$HH_MEM_MB" -lt 2048 ] && warn "mem_available ${HH_MEM_MB} MB (<2048) - admission gate blokuje claim (memory_low)" \
                                      || info "mem_available ${HH_MEM_MB} MB"
        fi
        [ -n "${HH_SWAP:-}" ] && [ "$(( HH_SWAP / 1048576 ))" -gt 256 ] && \
            warn "swap ${HH_SWAP} B wg snapshotu (>256 MB) - admission gate blokuje claim (swap_high)"
        [ -n "${HH_TEMPS:-}" ] && { [ "$HH_TEMPS" -gt 55 ] && warn "temp. dysku ${HH_TEMPS}C (>55)" || ok "temp. dysku max ${HH_TEMPS}C"; }
    fi

    # --- Snapshot procesow / CPU (top -bn1, sortowane wg %CPU) ---
    TOP=$(sect TOP)
    if [ -n "$TOP" ] && ! grep -qi 'VmSize' <<<"$TOP"; then
        echo -e "  ${DIM}snapshot host (busybox top; lista wg %VSZ = pamiec, %CPU tylko z 1 probki):${NC}"
        printf '%s\n' "$TOP" | sed 's/^/      /'
    else
        info "host: pelna lista procesow niedostepna po SSH (busybox) - patrz QTS > Resource Monitor"
    fi
fi

# ---------------------------------------------------------------------------
hdr "Kontenery Lenie (SSH + Docker)"
# ---------------------------------------------------------------------------
if ! nas_ssh 'echo ok' >/dev/null 2>&1; then
    warn "SSH niedostepny - pomijam kontrole kontenerow"
else
    DK=$(nas_ssh "
        D='${NAS_DOCKER}'
        if [ ! -x \"\$D\" ]; then D=docker; fi
        echo '===INSPECT==='
        for id in \$(\$D ps -aq --filter name=lenie); do
            \$D inspect -f '{{.Name}}|{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}-{{end}}|{{.RestartCount}}|{{.State.OOMKilled}}|{{.State.ExitCode}}' \"\$id\"
        done
        echo '===STATS==='
        \$D stats --no-stream --format '{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}|{{.MemPerc}}' 2>/dev/null | grep -i lenie
    " 2>/dev/null)

    dsect() { awk -v s="===$1===" 'f && /^===/{exit} $0==s{f=1;next} f' <<<"$DK"; }

    RUNNING=0; TOTAL=0
    while IFS='|' read -r name status health restarts oom exitcode; do
        [ -z "$name" ] && continue
        name="${name#/}"
        TOTAL=$((TOTAL + 1))
        case "$name" in *migrate*|*minio-init*) EXPECT_EXIT=true ;; *) EXPECT_EXIT=false ;; esac
        if [ "$status" = "running" ]; then
            RUNNING=$((RUNNING + 1))
            if [ "$health" = "unhealthy" ]; then
                crit "${name}: running ale UNHEALTHY"
            elif [ "$oom" = "true" ]; then
                crit "${name}: running, ale byl juz ubity przez OOM (OOMKilled=true)"
            elif [ "${restarts:-0}" -ge 3 ] 2>/dev/null; then
                warn "${name}: running, ale RestartCount=${restarts} - sprawdz logi"
            else
                ok "${name}: running${health:+ ($health)}  restarts=${restarts}"
            fi
        elif [ "$EXPECT_EXIT" = true ] && [ "$status" = "exited" ] && [ "${exitcode:-1}" = "0" ]; then
            ok "${name}: exited(0) - zadanie jednorazowe, OK"
        else
            crit "${name}: ${status}${exitcode:+ (exit ${exitcode})}${oom:+ OOMKilled=$oom}"
        fi
    done < <(dsect INSPECT)

    if [ "$TOTAL" -eq 0 ]; then
        crit "Nie znaleziono zadnych kontenerow 'lenie' - stack nie wstal (Container Station?)"
    else
        info "kontenerow: ${TOTAL}, running: ${RUNNING}"
    fi

    STATS=$(dsect STATS)
    if [ -n "$STATS" ]; then
        echo -e "  ${DIM}docker stats (CPU / RAM per kontener):${NC}"
        printf '%s\n' "$STATS" | awk -F'|' '{printf "      %-26s cpu %-8s mem %-22s %s\n",$1,$2,$3,$4}'
    fi
fi

# --- Logi backendu (opcjonalnie) ---
if [ "$DO_LOGS" = true ] && nas_ssh 'echo ok' >/dev/null 2>&1; then
    hdr "Ostatnie logi backendu"
    nas_ssh "D='${NAS_DOCKER}'; [ -x \"\$D\" ] || D=docker; \$D logs --tail 40 lenie-ai-server 2>&1" \
        2>/dev/null | sed 's/^/  /'
fi
fi   # DO_SSH

# ---------------------------------------------------------------------------
hdr "Podsumowanie"
# ---------------------------------------------------------------------------
if [ "$CRIT_COUNT" -eq 0 ] && [ "$WARN_COUNT" -eq 0 ]; then
    echo -e "  ${GREEN}NAS zdrowy - brak ostrzezen.${NC}"
    RC=0
elif [ "$CRIT_COUNT" -eq 0 ]; then
    echo -e "  ${YELLOW}${WARN_COUNT} ostrzezenie/a - warto zerknac, ale nic krytycznego.${NC}"
    RC=1
else
    echo -e "  ${RED}${CRIT_COUNT} problem(y) krytyczne, ${WARN_COUNT} ostrzezenie/a.${NC}"
    RC=2
fi
for n in "${NOTES[@]:-}"; do [ -n "$n" ] && echo "    - $n"; done

if [ "$RC" -ge 1 ]; then
    echo
    echo -e "  ${DIM}Dalej: QTS panel  http://${NAS_HOST}:8080  > System Logs / Resource Monitor${NC}"
    echo -e "  ${DIM}      historia CPU/RAM/swap i zdarzenia sprzed ostatniego restartu.${NC}"
fi

if [ "$DO_JSON" = true ]; then
    echo
    echo "{\"reachable\":true,\"backend_version\":\"${BACKEND_VER:-}\",\"warn\":${WARN_COUNT},\"crit\":${CRIT_COUNT},\"rc\":${RC}}"
fi

exit "$RC"
