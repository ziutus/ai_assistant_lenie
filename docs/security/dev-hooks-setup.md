# Secret-scanning git hooks — dev machine setup

`.pre-commit-config.yaml` defines the secret scanners that guard every commit and push, but a fresh clone does
not run any of them: git only executes hooks that were installed into `.git/hooks`, and the scanners themselves
are not installed by `uv sync`. Until this setup is done, commits and pushes go through **unscanned** (verification
report for the hooks themselves: [pre-commit-verification.md](pre-commit-verification.md)).

| Hook | Stage | Needs in PATH |
|---|---|---|
| gitleaks | pre-commit, pre-push | nothing (pre-commit builds it) |
| TruffleHog (`scripts/trufflehog-hook.sh`) | pre-commit, pre-push | `trufflehog` (local `language: system` hook — the hook fails if it is missing) |
| `scripts/scan-history-secrets.sh` | pre-push | `trufflehog`, `gitleaks`, `python3`, bash (Git Bash) |

`scan-history-secrets.sh` **skips a scanner that is missing from PATH with only a yellow warning** and still
exits 0, so a half-installed machine looks like a clean scan.

## Setup (Windows, once per clone)

Install the scanner binaries. Without admin rights, download the Windows release from GitHub, check its SHA-256
against the release's `checksums.txt`, and put the `.exe` in `~\.local\bin` (already in PATH). Match the versions to
`.pre-commit-config.yaml` / [pre-commit-verification.md](pre-commit-verification.md) (gitleaks v8.30.0,
TruffleHog v3.93.4):

```powershell
gh release download v8.30.0 -R gitleaks/gitleaks -p 'gitleaks_8.30.0_windows_x64.zip' -p 'gitleaks_8.30.0_checksums.txt'
gh release download v3.93.4 -R trufflesecurity/trufflehog -p 'trufflehog_3.93.4_windows_amd64.tar.gz' -p 'trufflehog_3.93.4_checksums.txt'
```

With admin rights, `choco install gitleaks trufflehog` works too.

Then, from the repo root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup-dev-hooks.ps1
```

The script installs `pre-commit` with `uv tool install`, warns about missing binaries, installs the
`pre-commit` and `pre-push` hooks, and runs every hook once against the whole tree (`-SkipRun` skips that; the
first run downloads hook environments and takes a while). It is safe to re-run.

Hooks live in the main checkout's `.git/hooks`, so worktrees under `.claude/worktrees/` share them — no per-worktree setup.

### How the TruffleHog hook scans

`scripts/trufflehog-hook.sh` replaces the upstream `trufflehog git file://. --since-commit HEAD` entry, which
failed in worktrees (`.git` is a file there: `repository does not exist`, exit 1, no finding) and on a normal
commit scanned nothing (`HEAD..HEAD`). Now:

- **pre-commit** exports the *staged* content (the index, so partial staging is honest) to a temp directory and runs
  `trufflehog filesystem` on it;
- **pre-push** scans the pushed range (`PRE_COMMIT_FROM_REF..PRE_COMMIT_TO_REF`, or the merge-base with
  `origin/main` for a new branch) with `trufflehog git` pointed at the **main checkout** — a real repository seen
  from any worktree (`file://<.git dir>` reads 0 chunks, `file://.` fails in a worktree);
- both pass `--no-update`: the self-updater cannot replace a running `trufflehog.exe` on Windows and made the hook exit 1
  with no finding.

The default result filter is `verified` (as before). To see how the hook reacts to an unverified canary:
`TRUFFLEHOG_RESULTS=verified,unverified,unknown bash scripts/trufflehog-hook.sh` (exit 183 = finding).
`scan-history-secrets.sh` points at the main checkout for the same worktree reason.

## Checking that it works

```powershell
Test-Path .git\hooks\pre-commit, .git\hooks\pre-push   # both True
pre-commit run --all-files
```
