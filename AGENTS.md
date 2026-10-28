# AGENTS.md — reguły operacyjne Lenie NAS

## Początek pracy: najnowszy remote

Na początku każdej pracy (przed pierwszą zmianą w kodzie, zakładaniem brancha
lub worktree) pobierz najnowszy stan zdalnego repozytorium: `git fetch origin`
i sprawdź `git log HEAD..origin/main`. Nową gałąź zakładaj z aktualnego
`origin/main`, a istniejącą gałąź przed wdrożeniem scal z `origin/main`.
Powód: NAS bywa wdrożony z nowszego `main` niż lokalny worktree, a wtedy
migracja Alembica kończy się błędem `Can't locate revision` (stan z
2026-10-24, rewizja `a9c4e7d1b362`).

## Koniec pracy: PR i uwagi z GitHuba przed wdrożeniem

Ostatni etap przed zgłoszeniem zmiany jako gotowej i przed wdrożeniem na NAS:
wypchnij branch, otwórz PR (draft wystarczy) i sprawdź uwagi z GitHuba. Dopiero
potem wdrażaj i zgłaszaj koniec. Powód: CodeQL i boty (np. alert „Incomplete URL
substring sanitization" w teście, PR #941) wychwytują rzeczy, które wymuszają
poprawkę kodu i drugie wdrożenie; wcześniejszy PR oszczędza ten drugi obieg.

- Po `gh pr create` poczekaj na wynik sprawdzeń: `gh pr checks <nr> --watch`
  (CodeQL trwa kilka minut).
- Przeczytaj uwagi: `gh api repos/ziutus/ai_assistant_lenie/pulls/<nr>/comments`,
  `.../pulls/<nr>/reviews` i `.../issues/<nr>/comments`.
- Każdą uwagę popraw (albo napisz w raporcie, dlaczego nie), ponów testy, wypchnij
  i dopiero wtedy wdróż. Nie wdrażaj z otwartym alertem, który dotyczy
  zmienionego kodu.
- Wyjątek: pilny hotfix na wyraźne polecenie użytkownika. Wtedy wdróż od razu,
  a uwagi z GitHuba sprawdź zaraz po wdrożeniu i zgłoś.
- Dotyczy to tylko zmian wdrażanych na NAS; zasady „tylko z domowej sieci LAN"
  poniżej pozostają bez zmian.

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
- Gdy użytkownik pracuje przez VPN (jest poza domem), **nie wdrażaj na NAS**:
  wdrożenie przez VPN jest wolne i zawodne (zrywa SSH i push do rejestru).
  Skończ pracę do commita/PR, zgłoś, że wdrożenie czeka, i wróć do niego, gdy
  użytkownik napisze, że jest w domu. Nie ponawiaj `nas-deploy.sh`, dopóki
  NAS nie odpowiada na `ssh admin@192.168.200.7` bez VPN-a, albo użytkownik
  wyraźnie nie poleci wdrożyć mimo VPN-a.
- **Jak sprawdzić, że użytkownik jest w domu:** komputer ma adres IPv4 z sieci
  `192.168.200.x` na fizycznej karcie (Ethernet / Wi-Fi), a nie na adapterze
  VPN. To lokalne sprawdzenie, które nie dotyka NAS-a (w odróżnieniu od
  `ssh`/`ping` na `192.168.200.7`, zabronionych wyżej):
  `Get-NetIPAddress -AddressFamily IPv4 | Where-Object IPAddress -like '192.168.200.*' | Select-Object InterfaceAlias, IPAddress`
  (PowerShell). Adres `192.168.200.x` na karcie fizycznej = w domu, można
  wdrażać (na tym komputerze to `vEthernet (Zewnetrzny1)`, most Hyper-V nad
  kartą fizyczną, nie VPN). Brak takiego adresu albo wynik tylko na adapterze VPN (WireGuard,
  OpenVPN, TAP, `tun`) = poza domem. Gdy użytkownik napisze, że jest w domu,
  a sprawdzenie temu przeczy, zapytaj, zamiast wdrażać.

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
