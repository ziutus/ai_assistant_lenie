# ============================================================================
# nas-health.ps1 - Wrapper PowerShell na nas-health.sh
#
# Cala logika jest w nas-health.sh (dziala z Git Bash / WSL). Ten wrapper
# tylko wygodnie odpala go z PowerShell i przekazuje kod wyjscia.
#
#   .\nas-health.ps1                # pelny raport (HTTP + SSH)
#   .\nas-health.ps1 -NoSsh         # tylko sondy sieciowe
#   .\nas-health.ps1 -Logs          # + ostatnie linie logu backendu
#   .\nas-health.ps1 -Json          # + zwiezle podsumowanie JSON
#
# LENIE_API_KEY z otoczenia (jesli ustawiony) jest przekazywany dalej.
# ============================================================================
[CmdletBinding()]
param(
    [switch]$NoSsh,
    [switch]$Logs,
    [switch]$Json
)

$ScriptDir = $PSScriptRoot
$Bash = "$ScriptDir/nas-health.sh"

# Preferuj Git Bash; pomin shimy WSL/Store (System32\bash.exe, WindowsApps),
# ktore wymagaja skonfigurowanej dystrybucji WSL.
$candidates = @()
$gitCmd = (Get-Command git -ErrorAction SilentlyContinue).Source
if ($gitCmd) {
    $gitRoot = Split-Path (Split-Path $gitCmd)      # ...\Git
    $candidates += (Join-Path $gitRoot "usr\bin\bash.exe")
    $candidates += (Join-Path $gitRoot "bin\bash.exe")
}
$candidates += "C:\Program Files\Git\usr\bin\bash.exe"
$candidates += "C:\Program Files\Git\bin\bash.exe"
$candidates += (Get-Command bash -All -ErrorAction SilentlyContinue |
    Where-Object { $_.Source -notmatch 'System32|WindowsApps' } |
    Select-Object -ExpandProperty Source)

$bashExe = $candidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $bashExe) {
    Write-Error "Nie znaleziono Git Bash. Uruchom bezposrednio: bash infra/docker/nas-health.sh"
    exit 127
}

$fwd = @()
if ($NoSsh) { $fwd += "--no-ssh" }
if ($Logs)  { $fwd += "--logs" }
if ($Json)  { $fwd += "--json" }

& $bashExe $Bash @fwd
exit $LASTEXITCODE
