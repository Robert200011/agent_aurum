[CmdletBinding()]
param(
    [string]$EnvFile = ".env",
    [string]$EvidenceDirectory = ".test-results/p6.5",
    [string]$StateDirectory = ".test-results/p6.5/runtime",
    [switch]$ReuseApiImage,
    [switch]$ReuseWebImage,
    [switch]$OfflineWebImage
)

$ErrorActionPreference = "Stop"
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$revision = (& git -C $repositoryRoot rev-parse HEAD).Trim()
$apiImage = "aurum-agent-api:p65-rehearsal"
$webImage = "aurum-agent-web:p65-rehearsal"
$env:AURUM_DEPLOY_ENVIRONMENT = "staging"
$env:AURUM_PUBLIC_DOMAIN = "http://127.0.0.1"
$env:AURUM_PUBLIC_ORIGIN = "http://localhost:18080"
$env:AURUM_OBJECT_STORAGE_PUBLIC_DOMAIN = "http://objects.localhost"
$env:AURUM_GATEWAY_HEALTH_HOST = "127.0.0.1"
$env:AURUM_GATEWAY_BIND = "127.0.0.1"
$env:AURUM_GATEWAY_HTTP_PORT = "18080"
$env:AURUM_GATEWAY_HTTPS_PORT = "18443"
$env:AURUM_PROMETHEUS_MAINTENANCE_PORT = "19090"
$env:AURUM_POSTGRES_MAINTENANCE_PORT = "15433"
$env:AURUM_MINIO_MAINTENANCE_PORT = "19002"
$certificateDirectory = [IO.Path]::GetFullPath(
    (Join-Path $repositoryRoot "$StateDirectory/minio-certs")
)
$certificatePath = Join-Path $certificateDirectory "public.crt"
$privateKeyPath = Join-Path $certificateDirectory "private.key"
New-Item -ItemType Directory -Path $certificateDirectory -Force | Out-Null
if (-not (Test-Path $certificatePath) -or -not (Test-Path $privateKeyPath)) {
    $opensslCommand = (Get-Command openssl -ErrorAction Stop).Source
    $opensslRoot = Split-Path (Split-Path $opensslCommand -Parent) -Parent
    $opensslConfig = Join-Path $opensslRoot "ssl/openssl.cnf"
    $opensslArguments = @(
        "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2",
        "-keyout", $privateKeyPath, "-out", $certificatePath, "-subj", "/CN=minio",
        "-addext", "subjectAltName=DNS:minio,DNS:localhost,IP:127.0.0.1"
    )
    if (Test-Path $opensslConfig) { $opensslArguments += @("-config", $opensslConfig) }
    & $opensslCommand @opensslArguments
    if ($LASTEXITCODE -ne 0) { throw "Unable to generate rehearsal MinIO certificate" }
}
$env:AURUM_MINIO_CERTS_DIR = $certificateDirectory.Replace("\", "/")
$env:AURUM_MINIO_CA_FILE = $certificatePath.Replace("\", "/")
$env:AWS_CA_BUNDLE = $certificatePath
$env:AURUM_OBJECT_STORAGE_INTERNAL_ENDPOINT = "https://minio:9000"
$env:AURUM_OBJECT_STORAGE_EXTERNAL_ENDPOINT = "http://objects.localhost:18080"
$env:AURUM_OBJECT_STORAGE_SECURE = "true"
$env:AURUM_REFRESH_TOKEN_COOKIE_SECURE = "false"
$env:AURUM_LANGGRAPH_AES_KEY = "0123456789abcdef0123456789abcdef"
$env:GRAFANA_ADMIN_PASSWORD = "p6.5-rehearsal-only"
$env:AURUM_BLUE_API_IMAGE = $apiImage
$env:AURUM_GREEN_API_IMAGE = $apiImage
$env:AURUM_BLUE_WEB_IMAGE = $webImage
$env:AURUM_GREEN_WEB_IMAGE = $webImage
$env:AURUM_ACTIVE_API_IMAGE = $apiImage
$env:AURUM_MIGRATION_IMAGE = $apiImage
$env:AURUM_RELEASE_STATE_DIR = [IO.Path]::GetFullPath((Join-Path $repositoryRoot $StateDirectory)).Replace("\", "/")

Push-Location $repositoryRoot
try {
    if ($ReuseApiImage) {
        docker tag aurum-agent-api:latest $apiImage
    } else {
        docker build --build-arg VCS_REF=$revision -t $apiImage .
    }
    if ($LASTEXITCODE -ne 0) { throw "API rehearsal image preparation failed" }
    if ($OfflineWebImage) {
        Push-Location web
        try {
            npm run build
            if ($LASTEXITCODE -ne 0) { throw "Host Web build failed" }
        }
        finally { Pop-Location }
        docker build -f Dockerfile.web.rehearsal --build-arg VCS_REF=$revision -t $webImage .
        if ($LASTEXITCODE -ne 0) { throw "Offline Web rehearsal image build failed" }
    } elseif (-not $ReuseWebImage) {
        docker build -f Dockerfile.web --build-arg VCS_REF=$revision -t $webImage .
        if ($LASTEXITCODE -ne 0) { throw "Web rehearsal image build failed" }
    }

    & (Join-Path $PSScriptRoot "release.ps1") -Mode rehearsal -CandidateSlot green `
        -ApiImage $apiImage -WebImage $webImage -EnvFile $EnvFile `
        -StateDirectory $StateDirectory -EvidenceDirectory $EvidenceDirectory `
        -ApproveCutover -StartStack
    if ($LASTEXITCODE -ne 0) { throw "Successful release rehearsal failed" }

    docker compose --env-file $EnvFile -f deploy/compose.production.yaml stop api-green
    if ($LASTEXITCODE -ne 0) { throw "Unable to inject candidate failure" }
    & (Join-Path $PSScriptRoot "rollback.ps1") -EnvFile $EnvFile `
        -StateDirectory $StateDirectory -EvidenceDirectory $EvidenceDirectory `
        -DrainSeconds 0
    if ($LASTEXITCODE -ne 0) { throw "Rollback rehearsal failed" }
    Write-Output "P6.5 success and forced-failure rollback rehearsals completed."
}
finally {
    Pop-Location
}
