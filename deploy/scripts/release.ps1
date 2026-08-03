[CmdletBinding()]
param(
    [ValidateSet("rehearsal", "production")][string]$Mode = "production",
    [ValidateSet("blue", "green")][string]$CandidateSlot = "green",
    [Parameter(Mandatory = $true)][string]$ApiImage,
    [Parameter(Mandatory = $true)][string]$WebImage,
    [string]$EnvFile = ".env",
    [string]$ComposeFile = "deploy/compose.production.yaml",
    [string]$StateDirectory = ".test-results/p6.5/runtime",
    [string]$EvidenceDirectory = ".test-results/p6.5",
    [string]$GatewayUrl = "http://127.0.0.1:18080",
    [string]$PrometheusUrl = "http://127.0.0.1:19090",
    [string]$Operator = $env:USERNAME,
    [string]$BackupEvidence,
    [string]$BackupDirectory,
    [string]$BackupReplicaDirectory,
    [switch]$ApproveCutover,
    [switch]$StartStack
)

$ErrorActionPreference = "Stop"
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$python = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
$composePath = [IO.Path]::GetFullPath((Join-Path $repositoryRoot $ComposeFile))
$envPath = [IO.Path]::GetFullPath((Join-Path $repositoryRoot $EnvFile))
$statePath = [IO.Path]::GetFullPath((Join-Path $repositoryRoot $StateDirectory))
$evidencePath = [IO.Path]::GetFullPath((Join-Path $repositoryRoot $EvidenceDirectory))
$releaseId = "p6.5-{0}-{1}" -f $Mode, (Get-Date -Format "yyyyMMddTHHmmss")
$manifestPath = Join-Path $evidencePath "$releaseId-manifest.json"
$observationPath = Join-Path $evidencePath "$releaseId-observation.json"
$metricsPath = Join-Path $evidencePath "$releaseId-metrics.json"
$decisionPath = Join-Path $evidencePath "$releaseId-decision.json"

New-Item -ItemType Directory -Path $statePath, $evidencePath -Force | Out-Null
$env:AURUM_RELEASE_STATE_DIR = $statePath.Replace("\", "/")
if ($CandidateSlot -eq "green") {
    $env:AURUM_GREEN_API_IMAGE = $ApiImage
    $env:AURUM_GREEN_WEB_IMAGE = $WebImage
} else {
    $env:AURUM_BLUE_API_IMAGE = $ApiImage
    $env:AURUM_BLUE_WEB_IMAGE = $WebImage
}

function Invoke-Compose {
    param([Parameter(Mandatory = $true)][string[]]$ComposeArguments)
    & docker compose --env-file $envPath -f $composePath @ComposeArguments
    if ($LASTEXITCODE -ne 0) { throw "Docker Compose failed with exit code $LASTEXITCODE" }
}

function Get-DeploymentValue {
    param([Parameter(Mandatory = $true)][string]$Name)
    $processValue = [Environment]::GetEnvironmentVariable($Name, "Process")
    if ($processValue) { return $processValue }
    $pattern = "^{0}=" -f [Regex]::Escape($Name)
    $line = Get-Content -LiteralPath $envPath -Encoding utf8 |
        Where-Object { $_ -match $pattern } | Select-Object -First 1
    if (-not $line) { return $null }
    return ($line -split "=", 2)[1]
}

Push-Location $repositoryRoot
try {
    if (-not (Test-Path -LiteralPath (Join-Path $statePath "active-upstream.caddy"))) {
        $initialSlot = if ($CandidateSlot -eq "green") { "blue" } else { "green" }
        & $python -m scripts.phase6_release activate --state-directory $statePath `
            --slot $initialSlot --release-id "$releaseId-initial"
        if ($LASTEXITCODE -ne 0) { throw "Unable to initialize release state" }
    }

    if ($StartStack) {
        Invoke-Compose -ComposeArguments @("up", "-d", "postgres", "redis", "minio", "otel-collector")
        Invoke-Compose -ComposeArguments @("run", "--rm", "--no-deps", "minio-init")
        Invoke-Compose -ComposeArguments @("--profile", "release", "run", "--rm", "migrate")
        Invoke-Compose -ComposeArguments @(
            "up", "-d", "--wait", "api-blue", "web-blue", "api-green", "web-green",
            "gateway", "worker", "beat", "prometheus", "grafana"
        )
    }

    if (-not $BackupEvidence) {
        if (-not $BackupDirectory) {
            if ($Mode -eq "production") {
                throw "Production release requires -BackupDirectory or -BackupEvidence"
            }
            $BackupDirectory = Join-Path $evidencePath "backups/primary"
        }
        if (-not $BackupReplicaDirectory) {
            if ($Mode -eq "production") {
                throw "Production release requires -BackupReplicaDirectory"
            }
            $BackupReplicaDirectory = Join-Path $evidencePath "backups/replica"
        }
        if ($Mode -eq "rehearsal" -and -not $env:AURUM_BACKUP_ENCRYPTION_KEY) {
            $keyBytes = New-Object byte[] 32
            $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
            try { $rng.GetBytes($keyBytes) } finally { $rng.Dispose() }
            $env:AURUM_BACKUP_ENCRYPTION_KEY = [Convert]::ToBase64String($keyBytes)
            $env:AURUM_BACKUP_KEY_ID = "p6.5-rehearsal-ephemeral"
        }
        $postgresPassword = Get-DeploymentValue -Name "POSTGRES_PASSWORD"
        if (-not $postgresPassword) { throw "POSTGRES_PASSWORD is missing from deployment env" }
        $encodedPassword = [Uri]::EscapeDataString($postgresPassword)
        $maintenancePort = if ($env:AURUM_POSTGRES_MAINTENANCE_PORT) {
            $env:AURUM_POSTGRES_MAINTENANCE_PORT
        } else { "15433" }
        $minioPort = if ($env:AURUM_MINIO_MAINTENANCE_PORT) {
            $env:AURUM_MINIO_MAINTENANCE_PORT
        } else { "19002" }
        $env:AURUM_MIGRATION_DATABASE_URL = `
            "postgresql+asyncpg://aurum:$encodedPassword@127.0.0.1:$maintenancePort/aurum"
        $objectStorageSecure = Get-DeploymentValue -Name "AURUM_OBJECT_STORAGE_SECURE"
        $minioScheme = if ($objectStorageSecure -eq "true") { "https" } else { "http" }
        if ($minioScheme -eq "https") {
            $minioCaFile = Get-DeploymentValue -Name "AURUM_MINIO_CA_FILE"
            if (-not $minioCaFile -or -not (Test-Path -LiteralPath $minioCaFile)) {
                throw "AURUM_MINIO_CA_FILE must reference a readable CA file for backup"
            }
            $env:AWS_CA_BUNDLE = [IO.Path]::GetFullPath($minioCaFile)
        }
        $env:AURUM_OBJECT_STORAGE_ENDPOINT = "$minioScheme`://127.0.0.1:$minioPort"
        $backupJson = (& (Join-Path $PSScriptRoot "backup.ps1") `
            -OutputDirectory $BackupDirectory -ReplicaDirectory $BackupReplicaDirectory `
            -EnvFile $EnvFile -ComposeFile $ComposeFile | Out-String)
        if ($LASTEXITCODE -ne 0) { throw "Pre-release backup failed" }
        $BackupEvidence = ($backupJson | ConvertFrom-Json).evidence
    }

    $manifestArguments = @(
        "-m", "scripts.phase6_release", "manifest", "--release-id", $releaseId,
        "--mode", $Mode, "--operator", $Operator, "--candidate-slot", $CandidateSlot,
        "--api-image", $ApiImage, "--web-image", $WebImage,
        "--migration-revision", "20260802_0012", "--backup-evidence", $BackupEvidence,
        "--output", $manifestPath
    )
    & $python @manifestArguments
    if ($LASTEXITCODE -ne 0) { throw "Release manifest validation failed" }

    $candidateService = "api-$CandidateSlot"
    Invoke-Compose -ComposeArguments @(
        "exec", "-T", $candidateService, "python", "-c",
        "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8010/api/v1/health/ready')"
    )

    & $python scripts/run_phase6_evaluation.py --output `
        (Join-Path $evidencePath "$releaseId-quality-gate.json")
    if ($LASTEXITCODE -ne 0) { throw "Phase 6 quality gate rejected the candidate" }

    if ($Mode -eq "production" -and -not $ApproveCutover) {
        Write-Output "Candidate is ready; production cutover requires -ApproveCutover."
        return
    }

    & $python -m scripts.phase6_release activate --state-directory $statePath `
        --slot $CandidateSlot --release-id $releaseId
    if ($LASTEXITCODE -ne 0) { throw "Unable to activate candidate slot" }
    Invoke-Compose -ComposeArguments @(
        "exec", "-T", "gateway", "caddy", "reload", "--config", "/etc/caddy/Caddyfile"
    )

    try {
        & $python -m scripts.phase6_release observe --url "$GatewayUrl/api/v1/health/ready" `
            --expected-slot $CandidateSlot --requests 20 --output $observationPath
        if ($LASTEXITCODE -ne 0) { throw "Canary HTTP observation failed" }
        & $python -m scripts.phase6_release metrics --prometheus-url $PrometheusUrl `
            --output $metricsPath
        if ($LASTEXITCODE -ne 0) { throw "Unable to collect canary metrics" }
        & $python -m scripts.phase6_release decide --observation $observationPath `
            --metrics $metricsPath --output $decisionPath
        if ($LASTEXITCODE -ne 0) { throw "Canary thresholds rejected the candidate" }
    }
    catch {
        $releaseError = $_
        & (Join-Path $PSScriptRoot "rollback.ps1") -EnvFile $EnvFile `
            -ComposeFile $ComposeFile -StateDirectory $StateDirectory `
            -GatewayUrl $GatewayUrl -EvidenceDirectory $EvidenceDirectory `
            -Operator $Operator -DrainSeconds 0
        if ($LASTEXITCODE -ne 0) {
            throw "$releaseError; automatic rollback also failed"
        }
        throw "$releaseError; rollback completed"
    }
    Write-Output "Release accepted: $releaseId; active slot: $CandidateSlot"
}
finally {
    Pop-Location
}
