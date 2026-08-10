[CmdletBinding()]
param(
    [ValidateSet("frontend", "app2", "backend", "worker", "document-worker", "db", "minio", "minio-init", "ner-service", "all")]
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
    "document-worker" = @{ Image = "lenie-ai-document-worker:latest"; RegistryImage = "$Registry/lenie-ai-document-worker:latest"; Dockerfile = "backend/Dockerfile"; Compose = "lenie-document-worker"; BuildArgs = @("--build-arg", "UV_EXTRA_ARGS=--extra docker --extra markdown") }
    db            = @{ Image = "lenie-ai-db:latest"; RegistryImage = "$Registry/lenie-ai-db:latest"; Dockerfile = "infra/docker/Postgresql/Dockerfile"; Compose = "lenie-ai-db" }
    "ner-service" = @{ Image = "lenie-ner-service:latest"; RegistryImage = "$Registry/lenie-ner-service:latest"; Dockerfile = "ner_service/Dockerfile"; Compose = "lenie-ner-service" }
    minio         = @{ Compose = "lenie-minio" }
    "minio-init"  = @{ Compose = "lenie-minio-init" }
}

if ($Service -contains "all") {
    $Services = @("db", "backend", "worker", "document-worker", "frontend", "app2")
} else {
    $Services = $Service
}

function Invoke-Checked {
    param([scriptblock]$Command, [string]$Description)
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$Description failed (exit code $LASTEXITCODE)." }
}

function Publish-ImageToNasRegistry {
    # Direct `docker push` to the NAS registry (192.168.200.7:5005) is the primary,
    # documented method (docs/CICD/NAS_Deployment.md) — requires the registry to be
    # configured as an insecure-registry in Docker Desktop's daemon.json:
    #   "insecure-registries": ["192.168.200.7:5005"]
    # (Settings -> Docker Engine -> edit JSON -> Apply & Restart). Falls back to the
    # save -> scp -> load-on-NAS -> local-push path (avoids a cross-network push
    # entirely) if the direct push fails — this covers two known intermittent Docker
    # Desktop bugs: "server gave HTTP response to HTTPS client" (insecure-registries
    # config lost, e.g. after a Docker Desktop update) and "file integrity checksum
    # failed for etc/apk/..." on Alpine-based images (storage layer corruption, see
    # docs/CICD/NAS_Deployment.md's troubleshooting section for the manual fix).
    # NOTE (2026-07-27): this fallback itself broke when local Docker Desktop was
    # on 29.6.1 vs the NAS's 27.1.2 - newer `docker save` emits an OCI blobs/ layout
    # that the older `docker load` can't read ("invalid tar header" / "invalid
    # diffID"). If direct push ever fails again, check Docker Desktop's version
    # drift from the NAS before assuming this fallback will save you.
    param([hashtable]$Definition, [string]$Name)
    docker tag $Definition.Image $Definition.RegistryImage
    docker push $Definition.RegistryImage
    if ($LASTEXITCODE -eq 0) { return }

    Write-Host "Direct push failed for $Name - falling back to save/scp/load-on-NAS" -ForegroundColor Yellow
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
                $BuildArgs = @($Def.BuildArgs)
                Invoke-Checked { docker build @BuildArgs --progress=plain -t $Def.Image -f $Def.Dockerfile . } "Build $Name"
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
if ($Services -contains "backend" -or $Services -contains "worker" -or $Services -contains "document-worker") {
    # lenie-migrate shares the backend image (lenie-ai-server:latest). Pulling the
    # requested service above doesn't guarantee that image is fresh — e.g. a
    # document-worker-only deploy pulls lenie-document-worker (a different image),
    # so without an explicit pull here migrate can silently run against a stale
    # cached lenie-ai-server:latest missing the migrations that were just pushed.
    Invoke-Checked { ssh "$NasUser@$NasHostName" "$NasDocker compose -f $NasComposeFile pull lenie-migrate" } "Pull lenie-migrate"
    Invoke-Checked { ssh "$NasUser@$NasHostName" "$NasDocker compose -f $NasComposeFile run --rm lenie-migrate" } "Database migrations"
}
$NamesArgument = $ComposeNames -join " "
Invoke-Checked { ssh "$NasUser@$NasHostName" "$NasDocker compose -f $NasComposeFile up -d $NamesArgument" } "Start services"
Invoke-Checked { ssh "$NasUser@$NasHostName" "$NasDocker compose -f $NasComposeFile ps $NamesArgument" } "Check services"

Write-Host "NAS deployment completed." -ForegroundColor Green
Write-Host ("Frontend: http://{0}:3000 | Backend: http://{0}:5055" -f $NasHostName)
