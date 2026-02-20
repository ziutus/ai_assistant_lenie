# Security: Dependabot Alert Review Process

This document describes how to review and resolve GitHub Dependabot security alerts for this project.

## Overview

GitHub Dependabot automatically scans project dependencies for known vulnerabilities (CVEs) and creates alerts. This project has dependencies across three ecosystems:

| Ecosystem | Location | Package Manager |
|-----------|----------|-----------------|
| Python | `backend/pyproject.toml`, `backend/uv.lock` | uv |
| Node.js (pnpm) | `web_interface_react/package.json`, `pnpm-lock.yaml` | pnpm |
| Node.js (npm) | `web_add_url_react/package.json`, `package-lock.json` | npm |

## How to Check Alerts

### Via GitHub CLI (recommended for Claude Code agent)

List all open alerts:
```bash
gh api repos/{owner}/{repo}/dependabot/alerts \
  --jq '.[] | select(.state=="open") | {number, severity: .security_vulnerability.severity, package: .security_vulnerability.package.name, summary: .security_advisory.summary}'
```

Get details for a specific alert (including fix version):
```bash
gh api repos/{owner}/{repo}/dependabot/alerts/{alert_number} \
  --jq '{package: .security_vulnerability.package.name, vulnerable_range: .security_vulnerability.vulnerable_version_range, first_patched: .security_vulnerability.first_patched_version.identifier, cve: .security_advisory.cve_id, manifest: .dependency.manifest_path}'
```

Group alerts by package:
```bash
gh api repos/{owner}/{repo}/dependabot/alerts \
  --jq '[.[] | select(.state=="open")] | group_by(.security_vulnerability.package.name) | .[] | {package: .[0].security_vulnerability.package.name, count: length, alerts: [.[].number], severity: .[0].security_vulnerability.severity, manifest: [.[].dependency.manifest_path] | unique}'
```

### Via GitHub Web UI

Navigate to: `https://github.com/{owner}/{repo}/security/dependabot`

## Review Decision Framework

### Step 1: Classify the dependency

| Type | Description | Action |
|------|-------------|--------|
| **Direct** | Listed in `pyproject.toml` or `package.json` | Update the version constraint and regenerate lock file |
| **Transitive** | Only in lock file, pulled by another dependency | Check if parent package has an update; if not, evaluate workarounds |
| **Dev-only** | Used only in development/build (e.g., `react-scripts`) | Lower priority — not exposed in production |

### Step 2: Assess severity and exploitability

- **HIGH + direct dependency + production code** — fix immediately
- **HIGH + transitive + no patch available** — document risk, plan migration
- **MEDIUM + direct** — update in next sprint
- **MEDIUM + transitive/dev-only** — batch with other updates

### Step 3: Check if a fix exists

Look at `first_patched_version` in the alert details:
- **Patch available** — update the dependency
- **No patch (`null`)** — check if the package can be replaced, or if the vulnerability is not exploitable in our context

## How to Fix Alerts

### Python dependencies (backend)

```bash
# 1. Update version in pyproject.toml (if pinned)
# 2. Regenerate lock file
cd backend && uv lock

# 3. Verify tests still pass
cd backend && PYTHONPATH=. uvx pytest tests/unit/ -v

# 4. Verify no new lint issues
uvx ruff check backend/
```

### Node.js dependencies (React apps)

```bash
# web_interface_react (pnpm)
cd web_interface_react && pnpm update <package-name>

# web_add_url_react (npm)
cd web_add_url_react && npm update <package-name>

# For transitive dependencies, use overrides:
# pnpm: add "pnpm.overrides" in package.json
# npm: add "overrides" in package.json
```

### Dismissing alerts

If an alert is not applicable (e.g., vulnerability requires conditions that don't exist in our usage):
```bash
gh api repos/{owner}/{repo}/dependabot/alerts/{number} \
  -X PATCH -f state=dismissed -f dismissed_reason="not_used" \
  -f dismissed_comment="Transitive dependency via react-scripts build toolchain, not used in production"
```

Valid `dismissed_reason` values: `fix_started`, `inaccurate`, `no_bandwidth`, `not_used`, `tolerable_risk`.

## Known Ongoing Issues

### CRA (Create React App) transitive dependencies

Both React apps use `react-scripts` (CRA), which pulls in vulnerable transitive dependencies:
- `jsonpath` (HIGH — no patch available, code injection via `react-scripts` → `bfj` → `jsonpath`)
- `nth-check` (HIGH — ReDoS)
- `webpack-dev-server` (MEDIUM — source code theft in dev mode)
- `postcss` (MEDIUM — parsing error)
- `ajv` (MEDIUM — ReDoS)

**Resolution:** Migrate both apps from CRA to Vite (backlog items B-16 and B-17). CRA is deprecated and no longer receives security updates.

**Risk assessment:** These are build-time/dev-time dependencies only. They are NOT included in the production bundle served to users. The `jsonpath` code injection vulnerability requires passing untrusted input to jsonpath expressions, which does not happen in the CRA build pipeline.

## Agent Permissions Required

When using Claude Code to review and fix Dependabot alerts, the agent needs the following permissions:

### Bash commands

| Command | Purpose |
|---------|---------|
| `gh api repos/{owner}/{repo}/dependabot/alerts` | Read Dependabot alerts |
| `gh api repos/{owner}/{repo}/dependabot/alerts/{id} -X PATCH` | Dismiss alerts |
| `cd backend && uv lock` | Regenerate Python lock file |
| `cd backend && PYTHONPATH=. uvx pytest tests/unit/ -v` | Run Python tests |
| `uvx ruff check backend/` | Run Python linter |
| `cd web_interface_react && pnpm update` | Update pnpm dependencies |
| `cd web_interface_react && pnpm audit` | Audit pnpm dependencies |
| `cd web_add_url_react && npm update` | Update npm dependencies |
| `cd web_add_url_react && npm audit` | Audit npm dependencies |

### Web access

| URL Pattern | Purpose |
|-------------|---------|
| `https://github.com/{owner}/{repo}/security/dependabot` | View alerts in browser |
| `https://nvd.nist.gov/vuln/detail/{CVE-ID}` | Check CVE details |
| `https://github.com/advisories/{GHSA-ID}` | Check GitHub Security Advisory details |
| `https://pypi.org/project/{package}/` | Check latest Python package versions |
| `https://www.npmjs.com/package/{package}` | Check latest npm package versions |

### File access

| File | Purpose |
|------|---------|
| `backend/pyproject.toml` | Read/edit Python dependency versions |
| `backend/uv.lock` | Read current locked versions |
| `web_interface_react/package.json` | Read/edit Node.js dependencies |
| `web_interface_react/pnpm-lock.yaml` | Read current locked versions |
| `web_add_url_react/package.json` | Read/edit Node.js dependencies |
| `web_add_url_react/package-lock.json` | Read current locked versions |

## Alert Review Log

| Date | Alert # | Package | Severity | Action | Notes |
|------|---------|---------|----------|--------|-------|
| 2026-02-20 | 171-173 | pypdf | medium | Updated to ≥6.7.1 | 3 CVEs fixed (CVE-2026-27024/25/26) |
| 2026-02-20 | 167-168 | jsonpath | high | Deferred to B-16/B-17 | No patch available; transitive via CRA; build-time only |
| 2026-02-20 | 169-170 | ajv | medium | Deferred to B-16/B-17 | Transitive via CRA; build-time only |
| 2026-02-20 | 29,60 | nth-check | high | Deferred to B-16/B-17 | Transitive via CRA |
| 2026-02-20 | 30,61 | postcss | medium | Deferred to B-16/B-17 | Transitive via CRA |
| 2026-02-20 | 53,54,80,81 | webpack-dev-server | medium | Deferred to B-16/B-17 | Dev-only; transitive via CRA |
