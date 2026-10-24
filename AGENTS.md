# AGENTS.md — reguły operacyjne Lenie NAS

## Początek pracy: najnowszy remote

Na początku każdej pracy (przed pierwszą zmianą w kodzie, zakładaniem brancha
lub worktree) pobierz najnowszy stan zdalnego repozytorium: `git fetch origin`
i sprawdź `git log HEAD..origin/main`. Nową gałąź zakładaj z aktualnego
`origin/main`, a istniejącą gałąź przed wdrożeniem scal z `origin/main`.
Powód: NAS bywa wdrożony z nowszego `main` niż lokalny worktree, a wtedy
migracja Alembica kończy się błędem `Can't locate revision` (stan z
2026-10-24, rewizja `a9c4e7d1b362`).

## Dostęp do NAS i wdrożenia

- SSH do NAS: zawsze użytkownik `admin` (`ssh admin@192.168.200.7`). Gołe
  `ssh 192.168.200.7` bez wpisu w `~/.ssh/config` łączy się jako lokalny
  użytkownik Windows i jest odrzucane. Zalecany wpis:
  `Host nas 192.168.200.7` / `HostName 192.168.200.7` / `User admin`
  (plik musi nazywać się `config`, nie `config.txt`).
- Wdrożenie: `bash ./infra/docker/nas-deploy.sh <usługa>` przez narzędzie Bash
  (nie `.ps1` przez PowerShell — `docker build` pisze na stderr). Użytkownik,
  host i ścieżka Dockera są na górze skryptu; szczegóły w
  [NAS_Deployment.md](docs/CICD/NAS_Deployment.md).
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
  uses it first; a live process keeps the directory locked (a leftover Codex
  `app-server-broker.mjs` node process started with the worktree as `--cwd` is
  the usual culprit — stop that one process, not other node processes).
- After the worktree is removed, delete its branch once the PR is merged into
  `main`: confirm with `gh pr view <number> --json state` (must be `MERGED`) or
  `git branch --merged origin/main`, then `git branch -d <branch>` (the safe
  form refuses an unmerged branch) and, if it still exists,
  `git push origin --delete <branch>`.
- Never use `git branch -D`, never delete a branch whose PR is still open or
  unmerged, and never delete `before_claude_code`. In any of those cases ask
  the user first.
- A sandboxed Codex run leaves `backend/.pytest_cache` ACL-locked (owned by the
  `CodexSandbox*` account), after which the worktree cannot be deleted without
  an elevated shell. `backend/` and `ner_service/` set
  `addopts = ["-p", "no:cacheprovider"]` in `pyproject.toml`, so pytest creates
  no cache; do not override it (`-p cacheprovider`) in a worktree. If a cleanup
  is denied anyway, stop and report the path, the owner and the ACL
  (`icacls`, `Get-Acl`); do not change ownership or permissions automatically.
