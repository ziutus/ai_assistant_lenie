# Container Image Scanning (Trivy)

`semgrep`/`bandit`/`pip-audit`/`safety` (see [dependency-supply-chain-scanning.md](dependency-supply-chain-scanning.md)) scan source code and Python dependency locks — they do not see vulnerabilities in the OS packages baked into a built Docker image (base image libraries, apt packages pulled in during build). Trivy fills that gap by scanning the built image itself.

## Why Trivy instead of migrating base images (e.g. to Chainguard)

Evaluated 2026-09-21: replacing base images project-wide with hardened/distroless images (e.g. Chainguard Images) was considered and rejected for `backend/`/`ner_service/` — those carry heavy C-extension dependencies (psycopg2, numpy/scipy, spaCy `pl_core_news_lg`) where a base-image change risks wheel/runtime-library incompatibilities for a benefit (fewer OS-level CVEs) that Trivy scanning already covers more cheaply, without touching the Dockerfiles. This is a single-household NAS deployment with no compliance/audit requirement driving hardened-base adoption.

## Usage

Build an image first, then scan it:

```bash
make nas-build-server && make security-trivy-server
make nas-build-frontend && make security-trivy-frontend
make nas-build-app2 && make security-trivy-app2
# or all three:
make nas-build-all && make security-trivy
```

Default severity filter is `HIGH,CRITICAL`; override with `TRIVY_SEVERITY=CRITICAL make security-trivy-server` for a narrower run. Requires Docker (runs `aquasec/trivy` via `docker run`, no local Trivy install needed).

## Finding triage

A finding is a starting point, not an action by itself — check whether a newer base image tag or an `apt`/`apk` upgrade in the Dockerfile resolves it, and re-scan after rebuilding. Not every reported CVE is exploitable in this deployment's context (household NAS, no public internet exposure of these images beyond what's already documented in `docs/deployment/nas/`); use judgment, but don't ignore `CRITICAL` findings in images that do get pushed to the NAS registry without at least recording why.
