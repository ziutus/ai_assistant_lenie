---
name: lenie-worktree-clean
description: Clean up finished Claude Code worktrees under .claude/worktrees/ on Windows - safely unlinks the shared .venv/node_modules junctions, removes merged worktrees and orphaned directories, and reports what needs manual or elevated action.
---

# Worktree cleanup

Invoke as `/lenie-worktree-clean` (preview first, then clean) or `/lenie-worktree-clean --dry`.
Instructions are in English; communicate with the user in Polish.

The work is done by `scripts/worktree-clean.ps1` (also `make worktree-clean`, and the
SessionEnd hook in `.claude/settings.json`). Do not re-implement it by hand with
`Remove-Item -Recurse` or a bare `git worktree remove`: on Windows PowerShell 5.1 both
follow the junctions to the main checkout's `.venv`, `.venv_wsl`, `ner_service/.venv`
and `web_interface_react/node_modules` (see AGENTS.md, "Git worktrees on Windows").

## Procedure

1. Run from the main checkout or any worktree (the script resolves the repo root itself):
   `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/worktree-clean.ps1 -DryRun`
2. Read the log lines and report them to the user as a table: `REMOVED/DRYRUN would remove`,
   `KEEP`, `SKIP`, `ORPHAN`, `PARTIAL`.
   - `KEEP ... unpushed/unmerged commits` = branch has commits that are not on a remote, not
     patch-equivalent on `origin/main`, and have no merged PR whose head equals HEAD.
     For each, look at `gh pr list --head <branch> --state all` and tell the user whether
     the PR is open (keep), closed without merge (ask), or merged with extra later commits.
   - `KEEP ... uncommitted changes` = list the files (`git -C <wt> status --short`) and ask
     whether they matter (logs/patches are usually disposable, but never delete without asking).
3. If the user agrees, run the same command without `-DryRun`.
4. Verify: `git worktree list`, list `.claude/worktrees/`, and confirm the main checkout
   still has `backend/.venv/Scripts/python.exe` and `web_interface_react/node_modules`.
5. Report what remains and why.

## Things the script cannot fix

- **`PARTIAL` / "still present ... ACL-locked"** - typically `backend/.pytest_cache` created by a
  sandboxed tool (Codex); even `icacls` is denied. This needs an elevated shell. Give the user
  the exact command from the log (`takeown /F <dir> /R /A /D Y; icacls <dir> /grant Administrators:F /T /C /Q; rmdir /s /q <dir>`)
  to run as Administrator (`! ` prefix does not elevate).
- **"file in use"** - another process holds a handle (an open editor/terminal/Claude session in
  that directory). Ask the user to close it, then rerun.
- **Locked worktrees whose pid is a live session** are skipped on purpose.

## Rules

- Never delete local branches without asking (the script only lists them).
- Never touch worktrees outside `.claude/worktrees/` (Codex ones live in `~/.codex/worktrees/`).
- Never use `--force` options or delete directories manually to "make it work" - if the script
  refuses because of an unexpected reparse point, show it to the user.
- Do not run the cleanup from inside the worktree being removed.
