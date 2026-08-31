#!/bin/sh
# NAS host-health collector for the Lenie worker admission gate.
#
# Run once per minute from QNAP Task Scheduler as an administrator account.
# Writes an atomic JSON snapshot that the workers read (read-only) from
# /run/lenie-host-health/host-health.json. See
# docs/deployment/nas/host-health-collector.md for installation steps.
#
# POSIX sh / BusyBox only: no bashisms, no `local`, no arrays. Reads
# /proc directly; tolerates a missing smartctl.
set -eu

OUTPUT_DIR="${HOST_HEALTH_OUTPUT_DIR:-/share/ContainerNew/lenie-host-health}"
OUTPUT="$OUTPUT_DIR/host-health.json"
STATE="$OUTPUT_DIR/.cpu-state"
mkdir -p "$OUTPUT_DIR"

# --- iowait: percentage of jiffies spent in iowait between the last two runs.
# /proc/stat is cumulative since boot, so a single sample is meaningless; we
# persist the previous totals in $STATE and report the delta.
set -- $(awk '/^cpu / { total=0; for (i=2; i<=NF; i++) total+=$i; print total, $6 }' /proc/stat)
TOTAL="${1:-0}"
IOWAIT="${2:-0}"
IOWAIT_PERCENT=0
if [ -r "$STATE" ]; then
    set -- $(cat "$STATE")
    PREVIOUS_TOTAL="${1:-0}"
    PREVIOUS_IOWAIT="${2:-0}"
    DELTA_TOTAL=$((TOTAL - PREVIOUS_TOTAL))
    DELTA_IOWAIT=$((IOWAIT - PREVIOUS_IOWAIT))
    if [ "$DELTA_TOTAL" -gt 0 ] && [ "$DELTA_IOWAIT" -ge 0 ]; then
        IOWAIT_PERCENT=$(awk -v io="$DELTA_IOWAIT" -v total="$DELTA_TOTAL" \
            'BEGIN { printf "%.2f", 100 * io / total }')
    fi
fi
printf '%s %s\n' "$TOTAL" "$IOWAIT" > "$STATE"

# --- memory / load, straight from /proc (values in bytes).
MEM_AVAILABLE=$(awk '/^MemAvailable:/ { print $2 * 1024 }' /proc/meminfo)
SWAP_USED=$(awk '/^SwapTotal:/ { total=$2 } /^SwapFree:/ { free=$2 } END { print (total - free) * 1024 }' /proc/meminfo)
LOAD_1=$(awk '{ print $1 }' /proc/loadavg)
: "${MEM_AVAILABLE:=0}"
: "${SWAP_USED:=0}"
: "${LOAD_1:=0}"

# --- disk temperatures: best effort. No smartctl on this NAS -> empty list,
# and the gate simply skips the temperature check.
SMARTCTL=$(command -v smartctl || true)
TEMPERATURES=""
if [ -n "$SMARTCTL" ]; then
    for DEVICE in /dev/sd? /dev/nvme?n?; do
        [ -b "$DEVICE" ] || continue
        # smartctl attribute formats vary wildly between drives; take the first
        # plausible standalone Celsius value (20-99) on any temperature line.
        TEMP=$("$SMARTCTL" -A "$DEVICE" 2>/dev/null | awk '
            /Temperature_Celsius|Airflow_Temperature|Current Drive Temperature|Temperature:/ {
                for (i = 1; i <= NF; i++) {
                    if ($i ~ /^[0-9][0-9]$/) { print $i; exit }
                }
            }') || true
        case "$TEMP" in
            ''|*[!0-9]*) ;;
            *) TEMPERATURES="${TEMPERATURES}${TEMPERATURES:+,}${TEMP}" ;;
        esac
    done
fi
if [ -n "$TEMPERATURES" ]; then
    TEMPERATURES_JSON="[$TEMPERATURES]"
else
    TEMPERATURES_JSON="[]"
fi

# --- write atomically: fully populate a temp file in the same directory, then
# rename it over the target so a reader never sees a partial document.
TEMP_FILE="$OUTPUT.$$.tmp"
printf '{"collected_at":"%s","load_1":%s,"mem_available_bytes":%s,"swap_used_bytes":%s,"iowait_percent":%s,"disk_temperatures_c":%s}\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$LOAD_1" "$MEM_AVAILABLE" "$SWAP_USED" "$IOWAIT_PERCENT" "$TEMPERATURES_JSON" \
    > "$TEMP_FILE"
mv "$TEMP_FILE" "$OUTPUT"
