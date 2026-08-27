# ADR-025: Host-aware admission control for NAS workers

**Date:** 2026-08-27
**Status:** Accepted
**Decision makers:** Ziutus

## Context

The QNAP TS-453Be is a 4-core, 16 GiB NAS shared with QTS and other services.
On 2026-08-27 its old disks suffered an I/O stall during QNAP maintenance.
Lenie's PostgreSQL queue was not the root cause, but workers have no mechanism
to avoid adding work while the host is already under pressure.  They claim
jobs independently, run with no global resource budget, and most long-running
jobs do not update their queue heartbeat after claim.

The current Compose file also has no CPU, memory, or PID limits.  A runaway
worker or service can therefore consume host resources needed by QTS and the
Docker runtime.

## Decision

### Host telemetry

QNAP Task Scheduler will run a small host-owned collector every minute.  It
writes its output atomically to
`/share/ContainerNew/lenie-host-health/host-health.json`.  The file is mounted
read-only into the workers and API process.

The snapshot format is versioned and contains its collection timestamp, load
averages, `MemAvailable`, swap use, iowait measured between samples, and disk
temperatures obtained by host tools.  The collector runs on the host because
it can safely use QNAP's SMART tooling and host `/proc` without giving a
container broad host visibility or extra privileges.

### Admission states

Every worker evaluates the newest snapshot before claiming a job:

| State | Condition | Behaviour |
|---|---|---|
| `normal` | all values below thresholds | claim under the global budget |
| `throttled` | host threshold exceeded | claim nothing; retry after 60 seconds |
| `light` | quiet hours | do not claim non-urgent heavy work |
| `unknown` | snapshot absent or older than 120 seconds | do not start heavy work; at most one light job |

Initial thresholds for the TS-453Be are load-1 greater than 2.5, available
memory below 2 GiB, swap above 256 MiB, iowait above 15% for two samples, or a
disk temperature at least 55 C.  A disk at 60 C is critical.  Values are
configuration, not code constants.

Quiet hours are initially `01:45-05:30 Europe/Warsaw`; non-urgent work stays
queued during this window.  API and search readiness remain independent from
worker admission, so a pressured host degrades background processing rather
than taking the application offline.

### Resource budget and recovery

Workers will use a PostgreSQL-backed, lease-based global budget of two work
units.  Heavy jobs (`obsidian_reimport`, `document_prepare`, and
`entity_enrichment`) consume both units; normal jobs consume one.  Claiming a
job and leasing its units must be atomic.  Completion releases leases, and a
periodic execution heartbeat renews them.  Stale recovery is therefore a
recovery path, not a false-positive timer for a slow but live job.

Each completed job is paced before the next claim.  The Obsidian watcher will
coalesce a large burst of file events into one full scan instead of enqueuing
one targeted job per file.

### Configuration and observability

Operational policy is held in Vault/environment configuration, not a new
database settings table.  It includes the snapshot path and freshness,
thresholds, quiet windows, weights, global capacity, heartbeat interval,
stale timeout, and inter-job delay.

Workers will publish their admission state; the API metrics endpoint will add
queue depth and age, attempts/failures, execution durations, admission state,
and snapshot age.  A separate worker-health endpoint signals degraded
background execution without changing `/readiness`.

### Immediate containment

Compose applies memory, CPU, and PID limits to every service.  Its normal
always-running maxima total about 10.6 GiB, preserving roughly 5 GiB for QTS,
filesystem cache, Docker overhead, and other NAS applications.  The
`legacy_aws_pull` remains enabled while its repeated failures are diagnosed in
a separate, evidence-driven change.  This ADR does not change its schedule or
the bridge's behaviour.

## Alternatives considered

- **Mount host `/proc` into every worker.** Rejected: it broadens container
  visibility and cannot reliably supply disk temperatures without further
  privileged access.
- **Privileged Docker sidecar.** Rejected: it adds a continuously running
  privileged process to the constrained NAS.  A QNAP-owned scheduled collector
  has less attack surface and is easier to inspect.
- **Redis/Celery or a commercial orchestration stack.** Rejected: PostgreSQL
  is already the durable queue and lease store; an additional control plane is
  disproportionate for this household NAS.
- **Fail all application readiness checks under host pressure.** Rejected:
  users should retain API and search access while background work is paused.

## Consequences

- QNAP Task Scheduler becomes a documented operational dependency and its
  snapshot freshness is itself monitored.
- A missing collector conservatively prevents new heavy jobs, but does not
  make Lenie unavailable.
- Resource limits can turn a process leak into a container restart rather
  than a host outage; limits must be observed and tuned after deployment.
- The legacy bridge needs a separate diagnosis and repair-or-retirement
  decision; this ADR deliberately does not change its schedule.
