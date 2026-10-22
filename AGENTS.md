# AGENTS.md — reguły operacyjne Lenie NAS

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
- **Deploy tylko z domowej sieci LAN, nigdy przez VPN.** NAS (`192.168.200.7`)
  wdrażamy wyłącznie wtedy, gdy użytkownik jest w domu, w tej samej sieci co
  NAS. Gdy jest poza domem (VPN włączony albo nie), nie wdrażaj na NAS
  (`nas-deploy.sh`, `ssh`/`docker` na NAS). Samo rozłączenie VPN nie pomaga:
  poza domem NAS jest po prostu nieosiągalny. Zrób kod, testy i commit
  lokalnie, a w raporcie napisz, że wdrożenie czeka na powrót użytkownika do
  domu (nie „na rozłączenie VPN"). Nie próbuj też „sprawdzać, czy NAS
  odpowiada" przez SSH i nie proś o włączanie lub wyłączanie VPN. Wyjątek tylko
  na wyraźne polecenie użytkownika w danej sesji.

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
