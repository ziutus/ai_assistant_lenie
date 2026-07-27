[CmdletBinding()]
param(
    [ValidateSet("frontend", "app2", "backend", "worker", "db", "minio", "ner-service", "all")]
    [string[]]$Service = @("all"),
    [switch]$SkipBuild,
    [switch]$ComposeOnly,
    [switch]$SyncCompose
)

$ErrorActionPreference = "Stop"

$NasHostName = "192.168.200.7"
$NasUser = "admin"
$NasDocker = "/share/CACHEDEV4_DATA/.qpkg/container-station/bin/docker"
$NasComposeDir = "/share/ContainerNew/lenie-compose"
$NasComposeFile = "$NasComposeDir/compose.nas.yaml"
$NasConfigDir = "/share/ContainerNew/lenie-config"
$Registry = "${NasHostName}:5005"
$ScriptDir = $PSScriptRoot
$ProjectRoot = (Resolve-Path (Join-Path $ScriptDir "..\..")).Path

$Definitions = @{
    frontend      = @{ Image = "lenie-ai-frontend:latest"; RegistryImage = "$Registry/lenie-ai-frontend:latest"; Dockerfile = "web_interface_react/Dockerfile"; Compose = "lenie-ai-frontend" }
    app2          = @{ Image = "lenie-ai-app2:latest"; RegistryImage = "$Registry/lenie-ai-app2:latest"; Dockerfile = "web_interface_app2/Dockerfile"; Compose = "lenie-ai-app2" }
    backend       = @{ Image = "lenie-ai-server:latest"; RegistryImage = "$Registry/lenie-ai-server:latest"; Dockerfile = "backend/Dockerfile"; Compose = "lenie-ai-server" }
    worker        = @{ Image = "lenie-ai-server:latest"; RegistryImage = "$Registry/lenie-ai-server:latest"; Dockerfile = "backend/Dockerfile"; Compose = "lenie-worker" }
    db            = @{ Image = "lenie-ai-db:latest"; RegistryImage = "$Registry/lenie-ai-db:latest"; Dockerfile = "infra/docker/Postgresql/Dockerfile"; Compose = "lenie-ai-db" }
    "ner-service" = @{ Image = "lenie-ner-service:latest"; RegistryImage = "$Registry/lenie-ner-service:latest"; Dockerfile = "ner_service/Dockerfile"; Compose = "lenie-ner-service" }
    minio         = @{ Compose = "lenie-minio" }
}

if ($Service -contains "all") {
    $Services = @("db", "backend", "worker", "frontend", "app2")
} else {
    $Services = $Service
}

function Invoke-Checked {
    param([scriptblock]$Command, [string]$Description)
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$Description failed (exit code $LASTEXITCODE)." }
}

function Publish-ImageToNasRegistry {
    param([hashtable]$Definition, [string]$Name)
    $archiveName = "lenie-deploy-{0}-{1}.tar" -f $Name, ([guid]::NewGuid().ToString("N"))
    $archive = Join-Path ([IO.Path]::GetTempPath()) $archiveName
    $remoteArchive = "$NasComposeDir/$archiveName"
    try {
        Invoke-Checked { docker save -o $archive $Definition.Image } "Save $Name"
        Invoke-Checked { scp $archive "$NasUser@$NasHostName`:$remoteArchive" } "Transfer $Name"
        $remote = "$NasDocker load -i $remoteArchive && $NasDocker tag $($Definition.Image) $($Definition.RegistryImage) && $NasDocker push $($Definition.RegistryImage) && rm -f $remoteArchive"
        Invoke-Checked { ssh "$NasUser@$NasHostName" $remote } "Publish $Name"
    } finally {
        if (Test-Path -LiteralPath $archive) { Remove-Item -LiteralPath $archive -Force }
    }
}

Write-Host "Lenie NAS Deploy (PowerShell)" -ForegroundColor Green
Write-Host "NAS: $NasHostName | Services: $($Services -join ', ')"

Invoke-Checked { ssh -o ConnectTimeout=5 "$NasUser@$NasHostName" "echo ok" } "SSH connection"

$SiteRules = Join-Path $ProjectRoot "backend\data\site_rules.json"
Invoke-Checked { ssh "$NasUser@$NasHostName" "mkdir -p $NasConfigDir" } "Create config directory"
$SiteRulesTarget = "{0}@{1}:{2}/site_rules.json" -f $NasUser, $NasHostName, $NasConfigDir
Invoke-Checked { scp $SiteRules $SiteRulesTarget } "Synchronizacja site_rules.json"

if ($SyncCompose) {
    $ComposeSource = Join-Path $ScriptDir "compose.nas.yaml"
    Invoke-Checked { ssh "$NasUser@$NasHostName" "mkdir -p $NasComposeDir" } "Create compose directory"
    $ComposeTarget = "{0}@{1}:{2}" -f $NasUser, $NasHostName, $NasComposeFile
    Invoke-Checked { scp $ComposeSource $ComposeTarget } "Synchronizacja compose.nas.yaml"
}

if (-not $ComposeOnly) {
    Invoke-Checked { docker info --format "Docker {{.ServerVersion}}" } "Check Docker Desktop"
    Invoke-Checked { curl.exe --silent --fail --connect-timeout 5 "http://$Registry/v2/" } "Check registry"

    Push-Location $ProjectRoot
    try {
        foreach ($Name in $Services) {
            $Def = $Definitions[$Name]
            if (-not $Def.Dockerfile) { continue }
            if (-not $SkipBuild) {
                Invoke-Checked { docker build --progress=plain -t $Def.Image -f $Def.Dockerfile . } "Build $Name"
            }
            Publish-ImageToNasRegistry -Definition $Def -Name $Name
        }
    } finally {
        Pop-Location
    }
}

$ComposeNames = @($Services | ForEach-Object { $Definitions[$_].Compose })
foreach ($ComposeName in $ComposeNames) {
    Invoke-Checked { ssh "$NasUser@$NasHostName" "$NasDocker compose -f $NasComposeFile pull $ComposeName" } "Pull $ComposeName"
}
if ($Services -contains "backend" -or $Services -contains "worker") {
    Invoke-Checked { ssh "$NasUser@$NasHostName" "$NasDocker compose -f $NasComposeFile run --rm lenie-migrate" } "Database migrations"
}
$NamesArgument = $ComposeNames -join " "
Invoke-Checked { ssh "$NasUser@$NasHostName" "$NasDocker compose -f $NasComposeFile up -d $NamesArgument" } "Start services"
Invoke-Checked { ssh "$NasUser@$NasHostName" "$NasDocker compose -f $NasComposeFile ps $NamesArgument" } "Check services"

Write-Host "NAS deployment completed." -ForegroundColor Green
Write-Host ("Frontend: http://{0}:3000 | Backend: http://{0}:5055" -f $NasHostName)
