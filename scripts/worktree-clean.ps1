<#
.SYNOPSIS
  Cleans up finished Claude Code worktrees under .claude/worktrees/.

.DESCRIPTION
  Two modes:
    -Cwd <path>   SessionEnd hook mode. Waits until the Claude process holding the
                  worktree lock exits, then cleans only the worktree containing <path>.
    (no -Cwd)     Sweep mode (`make worktree-clean`): cleans every worktree under
                  .claude/worktrees/ whose lock is stale or absent.

  A worktree is removed only when ALL of these hold:
    - no live process holds its lock (a lock whose pid is dead is removed first),
    - `git status` is clean (no modified or untracked files),
    - HEAD is already on a remote branch (nothing unpushed).
  Local branches are never deleted - they are only listed in the log.
  Worktrees outside .claude/worktrees/ (e.g. Codex ones) are never touched.
#>
[CmdletBinding()]
param(
    [string]$Cwd,
    [int]$WaitSeconds = 120,
    [switch]$DryRun
)

$ErrorActionPreference = 'Continue'

function Resolve-RepoRoot([string]$From) {
    $common = git -C $From rev-parse --path-format=absolute --git-common-dir 2>$null
    if (-not $common) { return $null }
    return (Split-Path -Parent ($common -replace '/', '\'))
}

$startDir = if ($Cwd) { $Cwd } else { (Get-Location).Path }
$repoRoot = Resolve-RepoRoot $startDir
if (-not $repoRoot) { exit 0 }
# Never keep a handle on a worktree directory we may be about to delete.
Set-Location $repoRoot

$wtRoot = (Join-Path $repoRoot '.claude\worktrees')
$logFile = Join-Path $repoRoot '.claude\worktree-clean.log'

function Write-Log([string]$Message) {
    $line = '{0:yyyy-MM-dd HH:mm:ss} {1}' -f (Get-Date), $Message
    Write-Host $line
    try { Add-Content -Path $logFile -Value $line -Encoding utf8 } catch {}
}

function Get-Worktrees {
    $items = @()
    $cur = $null
    foreach ($l in (git worktree list --porcelain)) {
        if ($l -like 'worktree *') {
            if ($cur) { $items += $cur }
            $cur = [ordered]@{ Path = ($l.Substring(9) -replace '/', '\'); Branch = $null; Locked = $false }
        } elseif ($l -like 'branch *') { $cur.Branch = $l.Substring(7) -replace '^refs/heads/', '' }
        elseif ($l -like 'locked*') { $cur.Locked = $true }
    }
    if ($cur) { $items += $cur }
    return $items
}

function Get-LockPid([string]$WorktreePath) {
    $name = Split-Path -Leaf $WorktreePath
    $lockFile = Join-Path $repoRoot ".git\worktrees\$name\locked"
    if (-not (Test-Path $lockFile)) { return $null }
    $text = Get-Content $lockFile -Raw
    if ($text -match 'pid (\d+)') { return [int]$Matches[1] }
    return 0  # locked, but not by a Claude session - leave alone
}

function Invoke-CleanWorktree($Wt) {
    $path = $Wt.Path
    $name = Split-Path -Leaf $path
    $lockPid = Get-LockPid $path

    if ($lockPid -eq 0) { Write-Log "SKIP $name - locked by something other than a Claude session"; return }
    if ($lockPid) {
        if (Get-Process -Id $lockPid -ErrorAction SilentlyContinue) {
            Write-Log "SKIP $name - session pid $lockPid is still running"; return
        }
    }
    if (-not (Test-Path $path)) { Write-Log "SKIP $name - directory missing (git worktree prune will handle it)"; return }

    $dirty = git -C $path status --porcelain
    if ($dirty) { Write-Log "KEEP $name - uncommitted changes"; return }
    $onRemote = git -C $path branch -r --contains HEAD 2>$null
    if (-not $onRemote) { Write-Log "KEEP $name - HEAD not on any remote branch (unpushed commits)"; return }

    if ($DryRun) { Write-Log "DRYRUN would remove $name (branch $($Wt.Branch))"; return }

    if ($lockPid) { git worktree unlock $path 2>$null }
    git worktree remove --force $path 2>$null | Out-Null
    # The directory can linger on Windows while another process still holds a handle.
    for ($i = 0; $i -lt 5 -and (Test-Path $path); $i++) {
        Start-Sleep -Seconds 1
        Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction SilentlyContinue
    }
    if (Test-Path $path) { Write-Log "PARTIAL $name - unregistered, directory still locked by another process: $path" }
    else { Write-Log "REMOVED $name" }
    if ($Wt.Branch) { Write-Log "  branch '$($Wt.Branch)' kept - delete it manually if no longer needed" }
}

$all = @(Get-Worktrees | Where-Object { $_.Path -like "$wtRoot\*" })

if ($Cwd) {
    # Hook mode: only the worktree containing $Cwd, and only after its session ends.
    $cwdNorm = ($Cwd -replace '/', '\').TrimEnd('\')
    $target = $all |
        Where-Object { $cwdNorm -eq $_.Path -or $cwdNorm -like "$($_.Path)\*" } |
        Sort-Object { $_.Path.Length } -Descending | Select-Object -First 1
    if (-not $target) { exit 0 }
    $lockPid = Get-LockPid $target.Path
    if ($lockPid) {
        $deadline = (Get-Date).AddSeconds($WaitSeconds)
        while ((Get-Process -Id $lockPid -ErrorAction SilentlyContinue) -and (Get-Date) -lt $deadline) {
            Start-Sleep -Seconds 1
        }
    }
    Start-Sleep -Seconds 2  # let handles on the directory drop
    Invoke-CleanWorktree $target
} else {
    foreach ($wt in $all) { Invoke-CleanWorktree $wt }
}

git worktree prune

# Orphaned directories (no longer registered) - remove only when clearly dead.
if (-not $Cwd -and (Test-Path $wtRoot)) {
    $registered = @(Get-Worktrees | ForEach-Object { $_.Path })
    foreach ($dir in Get-ChildItem $wtRoot -Directory -Force) {
        if ($registered -contains $dir.FullName) { continue }
        $gitFile = Join-Path $dir.FullName '.git'
        $dead = $true
        if (Test-Path $gitFile) {
            $gitdir = (Get-Content $gitFile -Raw) -replace '^gitdir:\s*', ''
            if (Test-Path $gitdir.Trim()) { $dead = $false }
        }
        if ($dead) {
            # Leftover husk only if nothing but dependency/cache dirs remains.
            $real = Get-ChildItem $dir.FullName -Recurse -Force -File -ErrorAction SilentlyContinue |
                Where-Object { $_.FullName -notmatch '\\(node_modules|\.venv|\.pytest_cache|__pycache__|\.ruff_cache)\\' } |
                Select-Object -First 1
            if ($real) { Write-Log "ORPHAN $($dir.Name) - contains files, left alone"; continue }
        }
        if ($dead -and -not $DryRun) {
            Remove-Item -LiteralPath $dir.FullName -Recurse -Force -ErrorAction SilentlyContinue
            if (Test-Path $dir.FullName) { Write-Log "ORPHAN $($dir.Name) - could not delete (in use)" }
            else { Write-Log "ORPHAN $($dir.Name) - deleted" }
        } elseif ($dead) { Write-Log "DRYRUN would delete orphan $($dir.Name)" }
        else { Write-Log "ORPHAN $($dir.Name) - not registered but its gitdir exists, left alone" }
    }
}
