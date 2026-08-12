[CmdletBinding()]
param(
    [Parameter()]
    [string]$Path = (Join-Path $PSScriptRoot '..')
)

$ErrorActionPreference = 'Stop'

if (-not (Get-Command depx -ErrorAction SilentlyContinue)) {
    [Console]::Error.WriteLine("depx was not found in PATH. Install a Windows release binary or build it from a local clone; see docs/security/dependency-supply-chain-scanning.md.")
    exit 2
}

$targetPath = (Resolve-Path -LiteralPath $Path).Path
Write-Host "Auditing dependencies for known malicious packages: $targetPath"

& depx audit $targetPath --require-clean
$depxExitCode = $LASTEXITCODE

if ($depxExitCode -ne 0) {
    exit $depxExitCode
}
