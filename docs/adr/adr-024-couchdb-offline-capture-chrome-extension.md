# ADR-024: CouchDB as a durable offline outbox for Chrome extension capture

**Date:** 2026-08-20
**Status:** Proposed — CouchDB deployed on NAS for hands-on testing; not yet wired into the extension or backend ingestion path
**Decision makers:** Ziutus

## Context

The Chrome extension (`web_chrome_extension/`) captures a page and POSTs it
directly to `/url_add` on the NAS backend (`x-api-key` auth, see
[web_chrome_extension/CLAUDE.md](../../web_chrome_extension/CLAUDE.md)). If
the NAS is unreachable — no VPN/relay path yet
([ADR-023](adr-023-gcloud-vpn-relay-nas-access.md) is accepted but
implementation is still pending), phone off the home Wi-Fi, NAS briefly
down — the POST fails immediately, the extension shows an alert, and the
capture is lost unless the user remembers to redo it by hand. There is no
local queue or retry today; `chrome.storage.local.sourcesCache` is the only
thing currently cached client-side, and that's just the source dropdown, not
captures.

Separately, the author uses CouchDB professionally and wants a real (if
narrow) use case inside Lenie to get hands-on experience with it, rather
than standing it up as a disconnected sandbox. CouchDB's defining feature —
native multi-master replication with a `_changes` feed and built-in conflict
handling — pairs with PouchDB (an IndexedDB-backed store that runs inside a
browser/extension) to give exactly the "write locally, sync automatically
once reachable" behavior this problem needs, without hand-rolling a retry
queue.

This is complementary to, not competing with, two things already decided:

- **ADR-023** solves *reachability* (getting a network path to the NAS from
  outside). This ADR solves *durability across periods with no
  reachability* — queue-and-retry instead of drop-on-failure. A full
  solution likely wants both.
- The job-queue direction in
  [storage-and-jobs-migration-plan.md](../deployment/nas/storage-and-jobs-migration-plan.md)
  (Postgres-backed queue + worker) is the right home for *server-side*
  async work once a document exists. It does not address the *browser-side*
  half of this problem — a queue that lives behind the same `/url_add`
  endpoint that's already unreachable doesn't help. CouchDB's role here is
  scoped narrowly to being a durable client-side outbox; it is not a second
  document store competing with PostgreSQL as source of truth.

## Decision

1. **Deploy a single-node CouchDB container on the NAS compose stack**
   (`infra/docker/compose.nas.yaml`) for hands-on testing now. Not yet
   wired to any production capture path.
   - No clustering — this validates the pattern, it isn't a plan for
     CouchDB HA.
   - Internal-only on `lenie-net` initially, same posture as
     `lenie-ner-service` — no port published to the NAS LAN/WAN until the
     design and auth are validated.
   - Persisted via a named `external: true` volume, matching every other
     stateful service in that file.
   - Credentials via a dedicated `couchdb.env` (not Vault) for the
     container's own bootstrap user, mirroring `minio.env` — the container
     needs its admin credentials before anything can reach Vault, same
     chicken-and-egg reason MinIO's are handled that way. Any future
     application-side consumer (a sync worker, etc.) still reads its
     connection credentials from Vault like everything else.
2. **Next phase (separate follow-up, not this ADR's initial scope):** a
   small proof-of-concept — PouchDB inside the Chrome extension, one-way
   replication to CouchDB on capture, and a worker that drains new CouchDB
   docs into the existing `/url_add` ingestion logic (reusing its
   validation, not duplicating it).
3. **Status stays "Proposed", not "Accepted"**, until the hands-on test
   confirms the pattern earns its complexity. This ADR records the plan and
   reasoning; the commit decision follows the prototype.

## Alternatives considered

- **Bespoke retry queue in the extension** (`chrome.storage.local` +
  periodic retry alarm). No new infrastructure, but re-implements — worse
  — what CouchDB/PouchDB replication already does (conflict handling,
  resumable sync, change feed). Rejected: the point of this exercise is
  hands-on CouchDB experience, and a bespoke queue defeats that.
- **Route through the planned Postgres job queue instead.** Rejected for
  the browser-side leg specifically — see Context above; it doesn't solve
  client-side durability when the server is unreachable. The job queue
  remains the right tool for the server-side half once a document exists.

## Consequences

- A new stateful service on the NAS stack to operate, monitor, and back up,
  alongside Postgres/MinIO/Vault.
- Once wired in (phase 2), any device the extension runs from caches
  unsynced captures locally (IndexedDB) — needs a cleanup/expiry story once
  a capture has synced.
- Cheap to unwind if the prototype doesn't earn its complexity: it stays
  out of the extension and backend entirely until deliberately wired in per
  Decision item 2.

## Open items for implementation

- Pin a specific CouchDB image tag (not `:latest`), matching the pinning
  discipline used for MinIO/registry images elsewhere in
  `compose.nas.yaml`.
- Decide whether direct browser→CouchDB replication is viable (needs
  public reachability, i.e. depends on ADR-023's relay landing) or whether
  a server-side intermediary sync path is simpler for phase 2.
- Decide conflict-resolution policy for CouchDB docs before more than one
  device/browser profile can write.
- Design the drain worker so it calls the existing ingestion path instead
  of duplicating `/url_add`'s validation/logic.
