<#
.SYNOPSIS
  Removes leftover worktree directories under .claude/worktrees/ that scripts/worktree-clean.ps1
  could not delete (ACL-locked .pytest_cache from a sandboxed tool). Needs Administrator rights.

.DESCRIPTION
  Run it yourself, no arguments needed:
    powershell -ExecutionPolicy Bypass -File scripts/worktree-clean-elevated.ps1
  If the shell is not elevated it relaunches itself through a UAC prompt (RunAs).

  A directory is a candidate only when ALL of these hold:
    - it lives directly under <repo>/.claude/worktrees/,
    - it is NOT registered in `git worktree list`,
    - after taking ownership, nothing is left in it except junk
      (.pytest_cache, __pycache__, a `.git` file, the known shared junctions).
  Directories with any other file are reported and left alone (they may hold unsaved work).
  Known shared junctions (.venv, .venv_wsl, node_modules) are unlinked with `cmd /c rmdir`
  BEFORE takeown/icacls/delete, because those follow links into the main checkout.
  Any other reparse point makes the script refuse that directory.
  Local branches are never touched.

.PARAMETER Name
  Limit the run to these directory names (default: every candidate).

.PARAMETER DryRun
  Only list what would be done; changes nothing (still asks for elevation).
#>
[CmdletBinding()]
param(
    [string[]]$Name,
    [switch]$DryRun,
    [switch]$NoPause
)

$ErrorActionPreference = 'Continue'

function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    return ([Security.Principal.WindowsPrincipal]$id).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if ($Name) { $Name = @($Name | ForEach-Object { $_ -split ',' } | Where-Object { $_ }) }

if (-not (Test-Admin)) {
    $argList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"")
    if ($Name) { $argList += @('-Name', ($Name -join ',')) }
    if ($DryRun) { $argList += '-DryRun' }
    Write-Host 'Requesting Administrator rights (UAC prompt)...'
    try {
        Start-Process -FilePath 'powershell.exe' -ArgumentList $argList -Verb RunAs -ErrorAction Stop
    } catch {
        Write-Host "Elevation was cancelled or failed: $($_.Exception.Message)"
        exit 1
    }
    exit 0
}

function Pause-Exit([int]$Code) {
    if (-not $NoPause) { Read-Host 'Press Enter to close' | Out-Null }
    exit $Code
}

# The script may sit in a worktree; the repo root is the parent of the common git dir.
$common = git -C $PSScriptRoot rev-parse --path-format=absolute --git-common-dir 2>$null
if (-not $common) { Write-Host 'Not inside a git repository.'; Pause-Exit 1 }
$repoRoot = Split-Path -Parent ($common -replace '/', '\')
Set-Location $repoRoot
$wtRoot = Join-Path $repoRoot '.claude\worktrees'
if (-not (Test-Path -LiteralPath $wtRoot)) { Write-Host "No $wtRoot"; Pause-Exit 0 }

$junctionRel = @('backend\.venv', 'backend\.venv_wsl', 'ner_service\.venv', 'web_interface_react\node_modules')
$junkNames = @('.pytest_cache', '__pycache__', '.git')

$registered = @(git worktree list --porcelain | Where-Object { $_ -like 'worktree *' } |
    ForEach-Object { ($_.Substring(9) -replace '/', '\').TrimEnd('\').ToLowerInvariant() })

function Remove-Junctions([string]$Path) {
    foreach ($rel in $junctionRel) {
        $p = Join-Path $Path $rel
        if (Test-Path -LiteralPath $p) {
            $item = Get-Item -LiteralPath $p -Force
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { cmd /c rmdir "`"$p`"" 2>$null | Out-Null }
        }
    }
}

function Test-Junk([string]$Path, [string]$Root) {
    # Junk = any path component that is a pytest/python cache or a pytest tmp dir (pytest-<n>, pytest-of-<user>).
    foreach ($part in $Path.Substring($Root.Length).TrimStart('\').Split('\')) {
        if (($junkNames -contains $part) -or ($part -like 'pytest-*')) { return $true }
    }
    return $false
}

function Get-Leftovers([string]$Path) {
    # Real files only: directories do not count, junk paths do not count.
    Get-ChildItem -LiteralPath $Path -Force -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { -not (Test-Junk $_.FullName $Path) }
}

$dirs = @(Get-ChildItem -LiteralPath $wtRoot -Directory -Force)
if ($Name) { $dirs = @($dirs | Where-Object { $Name -contains $_.Name }) }

$removed = 0; $skipped = 0
foreach ($d in $dirs) {
    $path = $d.FullName
    if ($registered -contains $path.ToLowerInvariant()) { continue }

    Remove-Junctions $path
    $reparse = @(Get-ChildItem -LiteralPath $path -Recurse -Force -Directory -Attributes ReparsePoint -ErrorAction SilentlyContinue)
    # pytest leaves `...current` links inside its tmp dirs; rmdir on a link never touches its target.
    foreach ($r in @($reparse | Where-Object { Test-Junk $_.FullName $path })) {
        if (-not $DryRun) { cmd /c rmdir "`"$($r.FullName)`"" 2>$null | Out-Null }
    }
    $reparse = @(Get-ChildItem -LiteralPath $path -Recurse -Force -Directory -Attributes ReparsePoint -ErrorAction SilentlyContinue |
        Where-Object { -not ($DryRun -and (Test-Junk $_.FullName $path)) })
    if ($reparse.Count -gt 0) {
        Write-Host "SKIP $($d.Name) - unexpected reparse point: $($reparse[0].FullName)"; $skipped++; continue
    }

    if ($DryRun) { Write-Host "DRYRUN would take ownership of and inspect $($d.Name)"; continue }

    # Safe now: no links are left, so /R cannot leave the directory.
    takeown /F "$path" /R /A /D Y 2>&1 | Out-Null
    icacls "$path" /grant 'Administrators:F' /T /C /Q 2>&1 | Out-Null

    $left = @(Get-Leftovers $path)
    if ($left.Count -gt 0) {
        Write-Host "SKIP $($d.Name) - contains real files (e.g. $($left[0].FullName)), left alone"; $skipped++; continue
    }

    cmd /c rmdir /s /q "`"$path`"" 2>$null | Out-Null
    if (Test-Path -LiteralPath $path) {
        Write-Host "FAILED $($d.Name) - still present (a process may hold it open)"; $skipped++
    } else {
        Write-Host "REMOVED $($d.Name)"; $removed++
    }
}

Write-Host "Done: removed $removed, left $skipped."
Pause-Exit 0
