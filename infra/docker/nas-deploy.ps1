[CmdletBinding()]
param(
    [ValidateSet("frontend", "app2", "backend", "db", "slack-bot", "minio", "mcp-server", "ner-service", "all")]
    [string[]]$Service = @("all"),
    [switch]$SkipBuild,
    [switch]$ComposeOnly,
    [switch]$SyncCompose
)

$ErrorActionPreference = "Stop"

$NasHostName = "192.168.200.7"
$NasUser = "admin"
$NasDocker = "/share/CACHEDEV4_DATA/.qpkg/container-station/usr/bin/.libs/docker"
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
    db            = @{ Image = "lenie-ai-db:latest"; RegistryImage = "$Registry/lenie-ai-db:latest"; Dockerfile = "infra/docker/Postgresql/Dockerfile"; Compose = "lenie-ai-db" }
    "slack-bot"   = @{ Image = "lenie-ai-slack-bot:latest"; RegistryImage = "$Registry/lenie-ai-slack-bot:latest"; Dockerfile = "slack_bot/Dockerfile"; Compose = "lenie-ai-slack-bot" }
    "mcp-server"  = @{ Image = "lenie-mcp-server:latest"; RegistryImage = "$Registry/lenie-mcp-server:latest"; Dockerfile = "infra/docker/Dockerfile.mcp"; Compose = "lenie-mcp-server" }
    "ner-service" = @{ Image = "lenie-ner-service:latest"; RegistryImage = "$Registry/lenie-ner-service:latest"; Dockerfile = "ner_service/Dockerfile"; Compose = "lenie-ner-service" }
    minio         = @{ Compose = "lenie-minio" }
}

if ($Service -contains "all") {
    $Services = @("db", "backend", "frontend", "app2")
} else {
    $Services = $Service
}

function Invoke-Checked {
    param([scriptblock]$Command, [string]$Description)
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$Description failed (exit code $LASTEXITCODE)." }
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
            Invoke-Checked { docker tag $Def.Image $Def.RegistryImage } "Tag $Name"
            Invoke-Checked { docker push $Def.RegistryImage } "Push $Name"
        }
    } finally {
        Pop-Location
    }
}

$ComposeNames = @($Services | ForEach-Object { $Definitions[$_].Compose })
foreach ($ComposeName in $ComposeNames) {
    Invoke-Checked { ssh "$NasUser@$NasHostName" "$NasDocker compose -f $NasComposeFile pull $ComposeName" } "Pull $ComposeName"
}
$NamesArgument = $ComposeNames -join " "
Invoke-Checked { ssh "$NasUser@$NasHostName" "$NasDocker compose -f $NasComposeFile up -d $NamesArgument" } "Start services"
Invoke-Checked { ssh "$NasUser@$NasHostName" "$NasDocker compose -f $NasComposeFile ps $NamesArgument" } "Check services"

Write-Host "NAS deployment completed." -ForegroundColor Green
Write-Host ("Frontend: http://{0}:3000 | Backend: http://{0}:5055" -f $NasHostName)
