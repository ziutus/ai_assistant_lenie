[CmdletBinding(DefaultParameterSetName = "Read")]
param(
    [Parameter(ParameterSetName = "Create", Mandatory = $true)]
    [switch]$Create,
    [Parameter(ParameterSetName = "Read", Mandatory = $true)]
    [switch]$Read
)

$ErrorActionPreference = "Stop"
$nasHost = "192.168.200.7"
$nasDocker = "/share/CACHEDEV4_DATA/.qpkg/container-station/bin/docker"
$keyName = "codex-read-only"
$secretDir = Join-Path $env:LOCALAPPDATA "Lenie"
$secretPath = Join-Path $secretDir "$keyName.dpapi"

function Invoke-NasPsql([string]$sql) {
    $remote = "$nasDocker exec lenie-ai-db psql -U postgres -d lenie-ai -At -v ON_ERROR_STOP=1 -c `"$sql`""
    return & ssh "admin@$nasHost" $remote
}

function Protect-Key([string]$key) {
    $plain = [Text.Encoding]::UTF8.GetBytes($key)
    try {
        $cipher = [Security.Cryptography.ProtectedData]::Protect(
            $plain, $null, [Security.Cryptography.DataProtectionScope]::CurrentUser
        )
        New-Item -ItemType Directory -Force -Path $secretDir | Out-Null
        [IO.File]::WriteAllBytes($secretPath, $cipher)
    } finally {
        [Array]::Clear($plain, 0, $plain.Length)
    }
}

function Unprotect-Key() {
    if (-not (Test-Path -LiteralPath $secretPath)) {
        throw "Brak lokalnego sekretu $secretPath. Utwórz go raz przez -Create."
    }
    $plain = [Security.Cryptography.ProtectedData]::Unprotect(
        [IO.File]::ReadAllBytes($secretPath), $null,
        [Security.Cryptography.DataProtectionScope]::CurrentUser
    )
    try {
        return [Text.Encoding]::UTF8.GetString($plain)
    } finally {
        [Array]::Clear($plain, 0, $plain.Length)
    }
}

function New-ReadOnlyKey() {
    $bytes = [byte[]]::new(32)
    [Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    try {
        return "lk_ro_" + (-join ($bytes | ForEach-Object { $_.ToString("x2") }))
    } finally {
        [Array]::Clear($bytes, 0, $bytes.Length)
    }
}

function Get-KeyHash([string]$key) {
    $bytes = [Text.Encoding]::UTF8.GetBytes($key)
    try {
        return -join ([Security.Cryptography.SHA256]::HashData($bytes) | ForEach-Object { $_.ToString("x2") })
    } finally {
        [Array]::Clear($bytes, 0, $bytes.Length)
    }
}

if ($Create) {
    if (Test-Path -LiteralPath $secretPath) {
        throw "Lokalny sekret już istnieje: $secretPath. Nie nadpisuję go."
    }
    if ((Invoke-NasPsql "SELECT 1 FROM api_keys WHERE name = '$keyName';") -contains "1") {
        throw "Klucz '$keyName' już istnieje w bazie. Nie można odzyskać jego plaintextu; usuń go świadomie albo wybierz nową nazwę."
    }

    # The local CSPRNG creates the plaintext. Only its SHA-256 is sent to and
    # persisted by PostgreSQL; the plaintext goes straight into DPAPI storage.
    $key = New-ReadOnlyKey
    $keyHash = Get-KeyHash $key
    $sql = "INSERT INTO api_keys (kind, user_id, name, key_hash, key_prefix, active) VALUES ('read_only', NULL, '$keyName', '$keyHash', '$($key.Substring(0, 12))', TRUE);"
    Invoke-NasPsql $sql | Out-Null
    try {
        Protect-Key $key
    } finally {
        $key = $null
        $keyHash = $null
    }
    Write-Output "Klucz read-only utworzony. Zaszyfrowany sekret zapisano w $secretPath"
    return
}

Unprotect-Key
