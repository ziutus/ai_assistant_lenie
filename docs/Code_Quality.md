# Code Quality & Security

Local development tools for linting, formatting, and security scanning.

> **Parent document:** [../CLAUDE.md](../CLAUDE.md) — full architecture reference.
> See also: [CI_CD_Tools.md](CI_CD_Tools.md) — CI pipeline tool integration.

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

## Pre-commit Hooks (TruffleHog)

Pre-commit hooks include TruffleHog for secret detection. See `.pre-commit-config.yaml`.
