---
name: 'security-check'
description: 'Run all security scanners (GitHub alerts, GitGuardian, gitleaks, trufflehog, semgrep, bandit, pip-audit, safety) and produce a unified security audit report saved to .claude/exports/'
---

You are a security auditor for Project Lenie. Your task is to run ALL available security tools and produce a unified audit report.

## Instructions

Execute the following 4 phases in order. Within each phase, run tools in parallel where possible. Each tool is independent — if one fails, continue with the rest and note the failure.

Create the `.claude/exports/` directory if it doesn't exist.

### Phase 1: GitHub API Security Alerts (~1s)

First, get the repo name dynamically:
```bash
git remote get-url origin | sed 's/.*github.com[:/]\(.*\)\.git/\1/' | sed 's/.*github.com[:/]\(.*\)/\1/'
```

Then run these 3 calls **in parallel** using the extracted `{owner}/{repo}`:

1. **Dependabot alerts** (open only):
```bash
gh api repos/{owner}/{repo}/dependabot/alerts --jq '[.[] | select(.state=="open")] | group_by(.security_vulnerability.package.name) | .[] | {package: .[0].security_vulnerability.package.name, count: length, alerts: [.[].number], severity: .[0].security_vulnerability.severity, manifest: [.[].dependency.manifest_path] | unique}'
```

2. **Secret scanning alerts**:
```bash
gh api repos/{owner}/{repo}/secret-scanning/alerts --jq '[.[] | select(.state=="open")] | length'
```
If this returns HTTP 404, note "Secret scanning not enabled for this repository".

3. **Code scanning alerts**:
```bash
gh api repos/{owner}/{repo}/code-scanning/alerts --jq '[.[] | select(.state=="open")] | length'
```
If this returns HTTP 404, note "Code scanning not enabled (no GHAS license or no CodeQL workflow configured)".

### Phase 2: GitGuardian MCP (~5s)

Use `ToolSearch` to find the `mcp__gitguardian__list_incidents` tool. If found, call it to list open incidents.

If the MCP server is unavailable or returns an error, note: "GitGuardian MCP unavailable (API key not configured or server not running)".

### Phase 3: Pre-commit Secret Detection (~30-60s)

Run these 2 commands **in parallel**:

1. **Gitleaks** (offline regex-based secret detection):
```bash
pre-commit run gitleaks --all-files 2>&1 || true
```

2. **TruffleHog** (online-verified secret detection):
```bash
pre-commit run trufflehog --all-files 2>&1 || true
```

If `pre-commit` is not installed, note: "pre-commit not available — skipping gitleaks and trufflehog scans".

### Phase 4: Local SAST & Dependency Scanners (~1-5min)

Run these 4 commands **in parallel**:

1. **Semgrep** (SAST — static analysis):
```bash
uvx semgrep scan --config=auto backend/ 2>&1 || true
```

2. **Bandit** (Python-specific security linter):
```bash
uvx bandit -r backend/ -x backend/tests,backend/.venv,backend/.venv_wsl -f json 2>&1 || true
```

3. **pip-audit** (Python dependency vulnerabilities):
```bash
cd backend && uvx pip-audit 2>&1 || true
```

4. **Safety** (Python dependency vulnerabilities, alternative database):
```bash
cd backend && uvx safety scan 2>&1 || true
```

If any tool is not installed or fails to run, note the failure and continue.

## Report Generation

After all phases complete, generate a unified markdown report with the following structure:

```markdown
# Security Audit Report — Project Lenie

**Date:** {YYYY-MM-DD}
**Branch:** {current git branch}
**Commit:** {short commit hash}

## Summary

| Tool | Status | Findings |
|------|--------|----------|
| GitHub Dependabot | ✅/❌/⚠️ | N open alerts |
| GitHub Secret Scanning | ✅/❌/⚠️ | N open alerts |
| GitHub Code Scanning | ✅/❌/⚠️ | N open alerts |
| GitGuardian | ✅/❌/⚠️ | N incidents |
| Gitleaks | ✅/❌/⚠️ | N findings |
| TruffleHog | ✅/❌/⚠️ | N findings |
| Semgrep | ✅/❌/⚠️ | N findings |
| Bandit | ✅/❌/⚠️ | N findings |
| pip-audit | ✅/❌/⚠️ | N vulnerabilities |
| Safety | ✅/❌/⚠️ | N vulnerabilities |

Status: ✅ = passed (0 findings), ⚠️ = findings detected, ❌ = tool unavailable/error

## 1. Secrets & Credentials

{Findings from: GitHub Secret Scanning, GitGuardian, Gitleaks, TruffleHog}
{If no findings: "No secret leaks detected across all scanners."}

## 2. Dependency Vulnerabilities

{Findings from: Dependabot, pip-audit, Safety}
{Group by severity: CRITICAL > HIGH > MEDIUM > LOW}
{Include package name, version, CVE, fix version if available}

## 3. Static Analysis (SAST)

{Findings from: Semgrep, Bandit, GitHub Code Scanning}
{Group by severity, include file:line references}

## 4. Recommendations

### IMMEDIATE (fix before next deploy)
{Critical/high severity items with known fixes}

### SOON (fix within current sprint)
{Medium severity items}

### PLANNED (add to backlog)
{Low severity or no-fix-available items}

{If no findings in any category: "No security issues detected — all clear!"}

## 5. Tool Coverage Notes

{List any tools that were unavailable and why}
{Suggestions for enabling missing tools}
```

Use the status indicators:
- ✅ = tool ran successfully, 0 findings
- ⚠️ = tool ran successfully, findings detected
- ❌ = tool was unavailable or errored

## Save the Report

Save the report to `.claude/exports/security-audit-{YYYY-MM-DD}.md`.

If a file with that name already exists, append a counter: `security-audit-{YYYY-MM-DD}-2.md`.

Display a brief summary to the user after saving, including:
- Total findings count per category (secrets, dependencies, SAST)
- Path to the saved report
- Top 3 most urgent items (if any)
