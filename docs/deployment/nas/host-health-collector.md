# NAS host-health collector & worker admission gate

The NAS runs the whole Lenie stack (API, PostgreSQL, MinIO, workers) on one
QNAP TS-453Be. When the box is already saturated — a big `document_prepare`
run, a QNAP backup job, a media re-index — pulling the next job just makes
things worse. The **worker admission gate** lets each worker skip claiming a
new job while the host is under pressure.

- Collector: [`infra/docker/nas/collect-host-health.sh`](../../../infra/docker/nas/collect-host-health.sh)
  runs on the QNAP host (not in a container) once per minute and writes
  `/share/ContainerNew/lenie-host-health/host-health.json`.
- Gate: [`backend/library/host_admission.py`](../../../backend/library/host_admission.py),
  called from `worker.py` right before `claim()`. All three worker services
  (`lenie-worker`, `lenie-document-worker`, `lenie-cloud-bridge`) mount the
  snapshot directory read-only at `/run/lenie-host-health`.

**The gate is disabled by default.** With `HOST_ADMISSION_ENABLED` unset (or
`false`) `evaluate()` always returns *allowed* and never touches the snapshot
file, so deploying this change is safe on its own. Nothing happens until an
operator has installed the collector, confirmed the snapshots, and flipped the
Vault flag. This does **not** change `/readiness` or any API/search behaviour.

## Snapshot format

`collect-host-health.sh` writes exactly this shape (all byte counts are bytes,
`collected_at` is UTC):

```json
{
  "collected_at": "2026-08-27T12:00:00Z",
  "load_1": 0.5,
  "mem_available_bytes": 4294967296,
  "swap_used_bytes": 0,
  "iowait_percent": 2.5,
  "disk_temperatures_c": [41, 43]
}
```

- `load_1` — 1-minute load average from `/proc/loadavg`.
- `mem_available_bytes` — `MemAvailable` from `/proc/meminfo`.
- `swap_used_bytes` — `SwapTotal - SwapFree` from `/proc/meminfo`.
- `iowait_percent` — iowait jiffies as a percentage of **total CPU jiffies
  between the last two collector runs**, not the cumulative value in
  `/proc/stat`. The collector keeps the previous totals in
  `/share/ContainerNew/lenie-host-health/.cpu-state`; the very first run after
  install reports `0` until it has two samples.
- `disk_temperatures_c` — best effort via `smartctl -A`. Empty list `[]` when
  `smartctl` is not installed or returns nothing; the gate then skips the
  temperature check.

The file is written atomically: the collector fills a `*.tmp` file in the same
directory and `mv`s it over `host-health.json`, so a worker never reads a
partial document.

## When the gate defers a claim

With `HOST_ADMISSION_ENABLED=true`, the worker logs
`job claim deferred reason=<reason> sleep=<n>s`, sleeps
`HOST_ADMISSION_THROTTLE_SECONDS`, and retries — it does not claim, execute, or
fail any job. The coordinator still runs `recover_stale()` and the scheduler
(so `feed_daily`, `legacy_aws_pull` and `obsidian_reimport` are still
*enqueued* on time), and the worker heartbeat keeps ticking so the container
healthcheck stays green.

| `reason` | Meaning |
|---|---|
| `host_health_unavailable` | snapshot file missing, unreadable, not valid JSON, or has no `collected_at` |
| `host_health_invalid` | snapshot parsed but a numeric field is the wrong type |
| `host_health_stale` | `collected_at` older than `HOST_HEALTH_MAX_AGE_SECONDS` (collector stopped) |
| `load_1_high` | `load_1 > WORKER_LOAD_1_MAX` |
| `memory_low` | `mem_available_bytes < WORKER_MEM_AVAILABLE_MIN_BYTES` |
| `swap_high` | `swap_used_bytes > WORKER_SWAP_USED_MAX_BYTES` |
| `iowait_high` | `iowait_percent > WORKER_IOWAIT_MAX_PERCENT` |
| `disk_temperature_high` | any value in `disk_temperatures_c > WORKER_DISK_TEMP_MAX_C` |

`reason=healthy` (allowed) is logged only at debug/normal claim time via the
existing `job start` lines — a deferred claim is the only WARNING this adds.

## Step 1 — install the collector on the QNAP host

1. Copy the script onto the NAS, next to the other Lenie compose assets:

   ```bash
   scp infra/docker/nas/collect-host-health.sh \
       admin@192.168.200.7:/share/ContainerNew/lenie-host-health/collect-host-health.sh
   ```

   Create the directory first if it does not exist
   (`ssh admin@192.168.200.7 'mkdir -p /share/ContainerNew/lenie-host-health'`).
   This is the same host path the compose file mounts into the workers.

2. Make it executable and give it a first run:

   ```bash
   ssh admin@192.168.200.7
   chmod +x /share/ContainerNew/lenie-host-health/collect-host-health.sh
   sh /share/ContainerNew/lenie-host-health/collect-host-health.sh
   cat /share/ContainerNew/lenie-host-health/host-health.json
   ```

   Confirm the JSON has all six fields and sane values. Run it a second time
   and check `iowait_percent` becomes a real number (the first run always
   reports `0`).

3. Register it in **QNAP Task Scheduler** (QTS: *Control Panel → System →
   Task Scheduler*):

   - *Create → Create a User-defined Script*.
   - **Task name**: `lenie-host-health`.
   - **User**: `admin` (needs read on `/proc` and, for disk temps, `smartctl`).
   - **Schedule**: *Custom* → run *Every 1 minute(s)*. If your QTS build only
     offers hourly/daily granularity in the GUI, use the crontab fallback
     below instead.
   - **Command**:

     ```sh
     sh /share/ContainerNew/lenie-host-health/collect-host-health.sh
     ```

   - Save. Select the task → *Run now* → *Results* to confirm exit code `0`.

   **crontab fallback** (also the way to make the schedule survive a firmware
   update — Task Scheduler entries usually do, hand-edited crontabs do not
   unless written to `/etc/config/crontab`):

   ```bash
   ssh admin@192.168.200.7
   echo '* * * * * sh /share/ContainerNew/lenie-host-health/collect-host-health.sh' >> /etc/config/crontab
   crontab /etc/config/crontab
   /etc/init.d/crond.sh restart
   ```

4. Let it run for a few minutes, then verify freshness from a dev machine or
   on the NAS:

   ```bash
   # age in seconds — must stay well under HOST_HEALTH_MAX_AGE_SECONDS (120)
   echo $(( $(date +%s) - $(date -d "$(python -c 'import json;print(json.load(open("/share/ContainerNew/lenie-host-health/host-health.json"))["collected_at"])')" +%s) ))
   ```

## Step 2 — add the workers' read-only mount

Already in [`infra/docker/compose.nas.yaml`](../../../infra/docker/compose.nas.yaml)
for `lenie-worker`, `lenie-document-worker` and `lenie-cloud-bridge`:

```yaml
    volumes:
      - /share/ContainerNew/lenie-host-health:/run/lenie-host-health:ro
```

Redeploy the stack (`infra/docker/nas-deploy.ps1` / `.sh`) so the workers pick
up the mount. Harmless while the gate is still disabled — nothing reads the
path yet.

## Step 3 — enable the gate in Vault

Only after Step 1 has produced **at least two** valid, fresh snapshots. Set
these in Vault (`secret/lenie/dev`) with
`MSYS_NO_PATHCONV=1 python scripts/env_to_vault.py vault set --env dev KEY=VALUE`:

| Variable | Default | Notes |
|---|---|---|
| `HOST_ADMISSION_ENABLED` | `false` | set to `true` to turn the gate on |
| `HOST_HEALTH_PATH` | `/run/lenie-host-health/host-health.json` | container-side path |
| `HOST_HEALTH_MAX_AGE_SECONDS` | `120` | snapshot older than this ⇒ `host_health_stale` |
| `WORKER_LOAD_1_MAX` | `2.5` | TS-453Be has 4 cores |
| `WORKER_MEM_AVAILABLE_MIN_BYTES` | `2147483648` | 2 GiB |
| `WORKER_SWAP_USED_MAX_BYTES` | `268435456` | 256 MiB |
| `WORKER_IOWAIT_MAX_PERCENT` | `15` | |
| `WORKER_DISK_TEMP_MAX_C` | `55` | |
| `HOST_ADMISSION_THROTTLE_SECONDS` | `60` | sleep between deferred claim attempts |

Restart the three worker services. Confirm normal operation: workers keep
processing jobs and you see no `job claim deferred` lines under a light load.
Then, in a maintenance window, point `HOST_HEALTH_PATH` at a deliberately
stale copy (or stop the collector) and confirm the workers log
`reason=host_health_stale` and stop claiming — then restore.

To disable again: set `HOST_ADMISSION_ENABLED=false` and restart the workers.
Leaving the collector and the mount in place is fine.
