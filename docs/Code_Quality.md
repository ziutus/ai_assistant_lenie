# Code Quality & Security

Local development tools for linting, formatting, and security scanning.

> **Parent document:** [../CLAUDE.md](../CLAUDE.md) — full architecture reference.
> See also: [CI_CD_Tools.md](CICD/CI_CD_Tools.md) — CI pipeline tool integration.

## Linting and Formatting (ruff)

```bash
make lint         # Run ruff linter
make lint-fix     # Run ruff with auto-fix
make format       # Format code with ruff
make format-check # Check formatting (for CI)
```

## Security Scanning

All security tools are run via `uvx` (uv tool runner) to avoid adding heavy dependencies to the project venv.

```bash
make security        # Run semgrep static analysis
make security-deps   # Check dependencies for vulnerabilities (pip-audit)
make security-bandit # Run bandit Python security linter
make security-safety # Check dependencies with safety
make security-all    # Run all security checks
```

| Tool | Purpose |
|------|---------|
| Semgrep | Static code analysis, security vulnerabilities |
| pip-audit | Dependency vulnerability scanning (PyPI advisory DB) |
| Bandit | Python-specific security linter |
| Safety | Dependency vulnerability check (requires free account) |

## Code Duplication Detection

Duplicate code detection helps identify copy-pasted blocks that should be extracted into shared functions or modules. The project already benefited from this approach — the `unified-config-loader` package (see [`shared_python/unified-config-loader/README.md`](../shared_python/unified-config-loader/README.md)) was extracted to eliminate ~300 lines of duplicated configuration code between `backend/` and `slack_bot/`.

```bash
make duplicate-check  # Detect duplicate code blocks (pylint, min 6 lines)
```

### Current tool: pylint `duplicate-code`

Uses pylint's built-in `similarities` checker (R0801). Detects blocks of ≥6 identical lines across Python files. Zero extra dependencies — runs via `uvx`.

### Tools for future consideration

| Tool | Language support | Description |
|------|-----------------|-------------|
| **jscpd** | 30+ languages (Python, TypeScript, etc.) | Universal copy-paste detector. Best for cross-language projects. `npx jscpd backend/ --min-lines 5` |
| **CPD (PMD)** | Python, Java, JS, and more | Mature copy-paste detector from Apache PMD suite |
| **SonarQube / SonarCloud** | All major languages | Full platform: duplication, coverage, security. Free for open-source |
| **Codeclimate** | All major languages | SaaS — duplication, complexity, maintainability metrics |

**Backlog item:** [B-81](../_bmad-output/planning-artifacts/epics/backlog.md) — Expand code duplication control (jscpd for cross-language, CI integration).

## Pre-commit Hooks (TruffleHog)

Pre-commit hooks include TruffleHog for secret detection. See `.pre-commit-config.yaml`.
