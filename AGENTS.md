# AGENTS.md — reguły operacyjne Lenie NAS

## Masowe operacje na Obsidianie

Nie uruchamiaj pełnego `obsidian_reimport` jako jednorazowej migracji na NAS-ie.
Stosuj małe, sekwencyjne partie i kontroluj obciążenie zgodnie z
[procedurą batch backfillu](docs/deployment/nas/obsidian-batch-backfill.md).

## Git worktrees on Windows

Claude Code creates worktrees under `.claude/worktrees/` (and Codex under
`~/.codex/worktrees/`). Claude's `worktree.symlinkDirectories` setting puts
junctions to the main checkout's `backend/.venv`, `backend/.venv_wsl`,
`ner_service/.venv` and `web_interface_react/node_modules` inside each one.
A recursive delete or a plain `git worktree remove` follows these junctions and
either fails ("file in use") or tries to delete the main checkout's
environments.

- Before removing a worktree, unlink every junction with `cmd /c rmdir <link>`
  (this never touches the target). List them with `cmd /c dir /AL /S /B <worktree>`.
  Do not use PowerShell 5.1 `Get-ChildItem -Recurse` for this — it follows
  junctions into the main checkout.
- Then run `git worktree remove --force <path>` (nested worktrees first) and
  `git worktree prune`.
- Remove a task's worktree right after its PR is merged. Close the session that
  uses it first; a live process keeps the directory locked.
- Delete only the worktree, never its branch, without asking the user.
