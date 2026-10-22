# Secret-scanning git hooks — dev machine setup

`.pre-commit-config.yaml` defines the secret scanners that guard every commit and push, but a fresh clone does
not run any of them: git only executes hooks that were installed into `.git/hooks`, and the scanners themselves
are not installed by `uv sync`. Until this setup is done, commits and pushes go through **unscanned** (verification
report for the hooks themselves: [pre-commit-verification.md](pre-commit-verification.md)).

| Hook | Stage | Needs in PATH |
|---|---|---|
| gitleaks | pre-commit, pre-push | nothing (pre-commit builds it) |
| TruffleHog | pre-commit, pre-push | `trufflehog` |
| `scripts/scan-history-secrets.sh` | pre-push | `trufflehog`, `gitleaks`, `python3`, bash (Git Bash) |

`scan-history-secrets.sh` **skips a scanner that is missing from PATH with only a yellow warning** and still
exits 0, so a half-installed machine looks like a clean scan.

## Setup (Windows, once per clone)

Install the scanner binaries (release binaries from GitHub, or Chocolatey if you use it):

```powershell
choco install gitleaks trufflehog
```

Then, from the repo root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup-dev-hooks.ps1
```

The script installs `pre-commit` with `uv tool install`, warns about missing binaries, installs the
`pre-commit` and `pre-push` hooks, and runs every hook once against the whole tree (`-SkipRun` skips that; the
first run downloads hook environments and takes a while). It is safe to re-run.

Hooks live in the main checkout's `.git/hooks`, so worktrees under `.claude/worktrees/` share them — no per-worktree setup.

## Checking that it works

```powershell
Test-Path .git\hooks\pre-commit, .git\hooks\pre-push   # both True
pre-commit run --all-files
```
