[CmdletBinding()]
param(
    # Skip the final `pre-commit run --all-files` smoke test.
    [Parameter()]
    [switch]$SkipRun
)

# Installs the secret-scanning git hooks defined in .pre-commit-config.yaml
# (gitleaks + TruffleHog on commit/push, scripts/scan-history-secrets.sh on push).
# Safe to re-run. See docs/security/dev-hooks-setup.md.

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    [Console]::Error.WriteLine("uv was not found in PATH. Install it first: https://docs.astral.sh/uv/getting-started/installation/")
    exit 2
}

if (-not (Get-Command pre-commit -ErrorAction SilentlyContinue)) {
    Write-Host "Installing pre-commit (uv tool install)..."
    & uv tool install pre-commit
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & uv tool update-shell
    $toolBin = (& uv tool dir --bin).Trim()
    $env:PATH = "$toolBin;$env:PATH"
}

# scan-history-secrets.sh (pre-push) silently skips a scanner that is not in PATH,
# so a missing binary means the push-time history scan does nothing. Warn loudly.
$missing = @()
foreach ($tool in 'gitleaks', 'trufflehog', 'python3') {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { $missing += $tool }
}
if ($missing.Count -gt 0) {
    Write-Warning ("Not in PATH: " + ($missing -join ', ') + ". The TruffleHog hook fails without trufflehog; the pre-push history scan skips missing scanners.")
    Write-Warning "gitleaks:   https://github.com/gitleaks/gitleaks/releases (or: choco install gitleaks)"
    Write-Warning "trufflehog: https://github.com/trufflesecurity/trufflehog/releases (or: choco install trufflehog)"
}

Push-Location $repoRoot
try {
    & pre-commit install --hook-type pre-commit --hook-type pre-push
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    if (-not $SkipRun) {
        # First run downloads/builds the hook environments, which takes a while.
        Write-Host "Running all hooks once against the whole tree..."
        & pre-commit run --all-files
        if ($LASTEXITCODE -ne 0) {
            [Console]::Error.WriteLine("pre-commit run reported findings or failures - review the output above.")
            exit $LASTEXITCODE
        }
    }
}
finally {
    Pop-Location
}

Write-Host "Secret-scanning hooks installed. New shells pick up the updated PATH."
