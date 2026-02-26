# Pre-Commit Secret Detection — Verification Report

> **Date:** 2026-02-26
> **Backlog item:** B-64
> **Origin:** Epic 19 retrospective — hardcoded API key committed in 478b62c
> **Tester:** Claude Opus 4.6 + Ziutus

## Tools Under Test

| Tool | Version | Detection Method | Stage |
|------|---------|------------------|-------|
| Gitleaks | v8.30.0 | Regex patterns + entropy analysis (offline) | pre-commit, pre-push |
| TruffleHog | v3.93.4 | Online verification of detected secrets | pre-commit, pre-push |

**Pre-commit framework:** pre-commit v4.0.1
**Custom config:** No `.gitleaks.toml` (default rules only)

## Test Results

### Test Matrix

| # | Secret Type | Example Pattern | Gitleaks | TruffleHog | Commit Blocked? |
|---|-------------|----------------|----------|------------|-----------------|
| 1 | AWS Access Key (example) | `AKIAIOSFODNN7EXAMPLE` | PASS (allowlisted) | PASS | NO |
| 2 | AWS Access Key (realistic) | `AKIA...` (20 chars) | **DETECTED** (aws-access-token) | PASS | YES |
| 3 | AWS Secret Key | 40 random chars | **DETECTED** (generic-api-key) | PASS | YES |
| 4 | OpenAI API Key | `sk-proj-...` | **DETECTED** (generic-api-key) | PASS | YES |
| 5 | RSA Private Key (PEM) | `-----BEGIN RSA PRIVATE KEY-----` | **DETECTED** (private-key) | PASS | YES |
| 6 | Slack Webhook URL | `https://hooks.slack.com/services/...` | **DETECTED** (slack-webhook-url) | PASS | YES |
| 7 | GitHub PAT | `ghp_...` (40 chars) | not detected (default) / **DETECTED** (with `.gitleaks.toml`) | PASS | YES (after fix) |
| 8 | Generic password | `DATABASE_PASSWORD=MyS3cret...` | not detected | PASS | NO |
| 9 | PostgreSQL URL with password | `postgresql://user:pass@host/db` | not detected | PASS | NO |
| 10 | Password in YAML config | `password: "Str0ng..."` | not detected | PASS | NO |

### Summary

- **Gitleaks:** Detected **5/10** secret types with default rules, **6/10** after adding `.gitleaks.toml` with GitHub PAT rule. Blocked commits containing high-entropy API keys, private keys, service-specific URLs, and (with custom rule) GitHub PATs.
- **TruffleHog:** Detected **0/10** — by design, it only flags *verified* (actually working) secrets. All test secrets were fake/invalid, so TruffleHog correctly passed them. This is expected behavior — TruffleHog would catch real compromised credentials.

### Detection Rate by Category

| Category | Detected | Total | Rate |
|----------|----------|-------|------|
| Cloud provider keys (AWS) | 2 | 3 | 67% |
| AI/API keys (OpenAI) | 1 | 1 | 100% |
| Cryptographic material (PEM) | 1 | 1 | 100% |
| Service webhooks (Slack) | 1 | 1 | 100% |
| Platform tokens (GitHub PAT) | 1 | 1 | 100% (after `.gitleaks.toml` fix) |
| Generic passwords | 0 | 3 | 0% |

## Findings

### What Works Well

1. **Gitleaks effectively blocks high-risk secrets** — AWS keys, OpenAI keys, private keys, and webhook URLs are caught before commit.
2. **TruffleHog provides defense in depth** — if a real (verified) secret somehow bypasses Gitleaks, TruffleHog would catch it during the verification step.
3. **Both tools run on pre-commit AND pre-push** — double gate prevents secrets from reaching the remote.
4. **Clear error messages** — Gitleaks output shows file, line, rule ID, and entropy, making triage easy.

### Gaps Identified

1. **GitHub PAT (`ghp_...`) not detected** — Gitleaks default rules do not match the `ghp_` prefix pattern (fine-grained PATs `github_pat_...` may also be missed).
2. **Generic passwords not detected** — `PASSWORD=value`, `password: "value"` in config files are invisible to both tools. This is a known trade-off: detecting passwords requires context-aware analysis that produces many false positives.
3. **Connection strings with embedded credentials not detected** — `postgresql://user:pass@host/db` format not matched.
4. **AWS example keys allowlisted** — `AKIAIOSFODNN7EXAMPLE` passes through. This is correct behavior (it's a known fake key), but means a developer who copy-pastes from AWS docs and replaces only part of the key could bypass detection if entropy is too low.

### Incident That Triggered B-64

The Epic 19 retrospective identified that a real API key was committed in 478b62c because pre-commit hooks were misconfigured at the time. The hooks have since been fixed and a second tool (Gitleaks) was added alongside TruffleHog. This verification confirms the fix is working for the most critical secret types (API keys, private keys, webhooks).

## Recommendations

### Immediate (Low Effort)

1. **Add `.gitleaks.toml` with GitHub PAT rule:**

```toml
# .gitleaks.toml
[extend]
# Extend default rules

[[rules]]
id = "github-pat"
description = "GitHub Personal Access Token"
regex = '''ghp_[A-Za-z0-9]{36}'''
tags = ["key", "github"]

[[rules]]
id = "github-fine-grained-pat"
description = "GitHub Fine-Grained Personal Access Token"
regex = '''github_pat_[A-Za-z0-9]{22}_[A-Za-z0-9]{59}'''
tags = ["key", "github"]
```

### Future (Medium Effort)

2. **Consider adding `detect-secrets` (Yelp)** as a third tool — it uses a different detection approach (high-entropy string detection + plugin-based keyword scanning) that catches some patterns Gitleaks misses.

3. **Periodic rotation of the API key** that was committed in 478b62c — even though removed in 5c57356, the key exists in git history.

### Accepted Risks

- **Generic passwords in config files** — Not feasible to detect without unacceptable false positive rate. Mitigated by: (a) `.env` files in `.gitignore`, (b) Epic 20 migrating secrets to Vault/SSM, (c) developer discipline.
- **Connection strings with embedded passwords** — Same trade-off. Mitigated by Epic 20 removing passwords from config files entirely.

## Conclusion

The pre-commit secret detection setup is **functional and effective** for the most critical secret types. Gitleaks provides fast, offline regex+entropy detection that blocks commits. TruffleHog adds verification-based detection for real credentials. The combination provides adequate defense in depth for a single-developer project.

The main gap (GitHub PAT detection) can be closed with a simple `.gitleaks.toml` custom rule. Generic password detection is an accepted risk mitigated by Epic 20 (secrets to Vault/SSM).

**Verdict:** PASS — `.gitleaks.toml` added with GitHub PAT rules, verified working.
