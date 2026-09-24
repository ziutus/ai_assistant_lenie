# NAS incident runbook

What to check when the NAS misbehaves, after any restart, and before a deploy.
Current state and procedures only — this is not an incident log.

## 1. Quick status

```bash
make nas-health                                    # full snapshot (network, HTTP, kernel, RAID, data paths, Vault, containers)
bash infra/docker/nas-deploy.sh --preflight-only   # the same blockers the deploy checks, no side effects
```

Exit code of `nas-health.sh`: `0` healthy, `1` warnings, `2` critical / NAS unreachable.
Both tools only read from the NAS.

## 2. What is checked, and why

| Check | Where | Blocks a deploy? | Why it matters |
|---|---|---|---|
| Kernel oops / panic / hung task in `dmesg` (`Oops:`, `BUG:`, `unable to handle page fault`, `Call Trace`) | `nas-health.sh`, preflight | yes | `dockerd` on a kernel that has oopsed can hang in the middle of a layer extraction, and the NAS may crash and reboot shortly after |
| `docker info` answers | preflight | yes | a hung Docker daemon blocks `pull`/`up` forever |
| `/share/Container` holds `lenie-compose/compose.nas.yaml`, `lenie-env/.env`, `vault/config/vault.hcl` | `nas-health.sh`, preflight | yes | missing bind-mount sources make Docker create empty directories (see 3.2) |
| RAID (`/proc/mdstat`): a member missing | `nas-health.sh`, preflight | yes | degraded array; `md9` (QNAP system array, 32 slots) is ignored |
| RAID resync / recovery running | `nas-health.sh`, preflight | no (warning) | disk I/O is busy, pulls and the load average are worse until it finishes |
| Data disk ≥ 95 % | preflight | yes | image extraction fails half-way |
| Vault sealed, unreachable or restart-looping | `nas-health.sh`, preflight | yes | backend and workers cannot read secrets |
| Uptime < 10 min | preflight | no (warning) | services are still settling after a boot |
| Crontab line for `collect-host-health.sh` points to a missing file | `nas-health.sh`, preflight | no (warning) | `host-health.json` goes stale and the admission gate holds workers |

`--skip-preflight` continues past blockers (at your own risk).

## 3. Failure modes

### 3.1 Kernel oops in `dockerd`

- **Symptoms:** `docker compose pull` stops at the same point (e.g. a large layer at
  99 %, later `unexpected EOF`) while the NAS is idle (`top`: CPU idle, no I/O);
  `dmesg` shows an oops with `Comm: dockerd`; later the NAS may reboot on its own.
- **Do not** kill and retry pulls in a loop, and do not start a second deploy — it
  only piles up hung `docker compose pull` processes on the NAS.
- **Do:** confirm with `dmesg | grep -E 'Oops:|BUG:'`, let the NAS reboot (or reboot it
  from QTS), then run the post-reboot checklist (section 4). The oops is cleared from
  `dmesg` by the reboot; the past event stays in QTS → System Logs.

### 3.2 Bind-mount source missing → Docker creates an empty directory

- **Symptoms:** `lenie-vault` restart-loops with `A storage backend must be specified`;
  workers fail with `Failed to load config from Vault`; a bind-mount directory has an
  empty listing and a creation time equal to the boot time.
- **Cause:** compose bind-mounts host paths. If the path does not exist when Docker
  starts a container, Docker silently creates an **empty** directory there instead of
  failing. Only `/share/Container` (a QTS-managed share, recreated by the system at
  every boot) may be used in compose, scripts and crontab — never a hand-made symlink
  such as the former `/share/ContainerNew`, which is not recreated after a reboot.
- **Do:** make sure `/share/Container` exists and holds the data (real location
  `/share/CACHEDEV2_DATA/Container`; check QTS → Control Panel → Shared Folders if it
  is missing). Remove the empty directories Docker created (only if they are empty:
  `rmdir` refuses otherwise), then `docker restart lenie-vault` and let the dependent
  services restart. Vault auto-unseals from its stored key.
- **Never** point anything at `Pool1_migrated/ContainerNew/...` — those are empty
  leftovers of the Pool1 → Pool2 migration.

### 3.3 RAID resync after an unclean shutdown

Expected after a crash or power loss: `md2_resync` runs for hours, `nas-health.sh`
shows a WARN with the progress and estimate. Nothing to fix — expect a higher load
and slower pulls. Check `grep -A2 '^md' /proc/mdstat` for the percentage.

### 3.4 Stuck deploy lock

`nas-deploy.sh` allows one deploy at a time (`mkdir` lock on the NAS:
`/share/Container/lenie-compose/.nas-deploy.lock`, owner = `host|pid|epoch|user`).
A lock is taken over automatically when its owner is a dead process on the same
machine or when it is older than 2 h (`LENIE_DEPLOY_LOCK_MAX_AGE`). Otherwise:

```bash
bash infra/docker/nas-deploy.sh --force-unlock <services>
# or by hand, only if you are sure no deploy runs:
ssh admin@192.168.200.7 'rm -rf /share/Container/lenie-compose/.nas-deploy.lock'
```

### 3.5 NAS crontab still points to `/share/ContainerNew`

`nas-health.sh` reports a WARN when the `collect-host-health.sh` path in
`/etc/config/crontab` does not exist. Migrate the line once:

```bash
ssh admin@192.168.200.7
sed -i 's#/share/ContainerNew/#/share/Container/#' /etc/config/crontab
crontab /etc/config/crontab
/etc/init.d/crond.sh restart
```

See [host-health-collector.md](host-health-collector.md) for the collector itself.

## 4. After any NAS restart

1. `make nas-health` — expect no CRITICAL. Read the `System` section first
   (uptime, RAID, `/share/Container`, dmesg).
2. If `/share/Container` is incomplete or Vault restarts: section 3.2.
3. Wait until `lenie-vault` is `healthy` and `/healthz` answers `200`, then check that
   the containers are running with a low restart count.
4. Only then deploy: `bash infra/docker/nas-deploy.sh <services>`.

## 5. Deploy notes

- A live log is always written to `$TMPDIR/lenie-nas-deploy-<time>.log` (path printed
  first). Do not pipe the deploy through `| tail` — it shows nothing until the script
  ends; use the log file or `| tee`.
- The QNAP shell has no `timeout` and no `flock`; wrap `ssh` with a local `timeout`
  and use `mkdir` for locking (as the script does).
- Backend, `worker` and `cloud-bridge` share one image: deploy `backend` (build + push
  + migrations), then `--skip-build worker cloud-bridge`. `document-worker` and
  `ner-service` have their own images.
- `nas-deploy.ps1` has none of the preflight / lock / log features — use
  `nas-deploy.sh` (Git Bash).
