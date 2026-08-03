[CmdletBinding()]
param(
    [string]$EnvFile = ".env",
    [string]$ComposeFile = "deploy/compose.production.yaml",
    [string]$StateDirectory = ".test-results/p6.5/runtime",
    [string]$EvidenceDirectory = ".test-results/p6.5",
    [string]$GatewayUrl = "http://127.0.0.1:18080",
    [string]$Operator = $env:USERNAME,
    [ValidateRange(0, 600)][int]$DrainSeconds = 30
)

$ErrorActionPreference = "Stop"
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$python = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
$composePath = [IO.Path]::GetFullPath((Join-Path $repositoryRoot $ComposeFile))
$envPath = [IO.Path]::GetFullPath((Join-Path $repositoryRoot $EnvFile))
$statePath = [IO.Path]::GetFullPath((Join-Path $repositoryRoot $StateDirectory))
$evidencePath = [IO.Path]::GetFullPath((Join-Path $repositoryRoot $EvidenceDirectory))
$releaseId = "p6.5-rollback-{0}" -f (Get-Date -Format "yyyyMMddTHHmmss")
$env:AURUM_RELEASE_STATE_DIR = $statePath.Replace("\", "/")

Push-Location $repositoryRoot
try {
    $stateJson = (& $python -m scripts.phase6_release rollback --state-directory $statePath `
        --release-id $releaseId | Out-String)
    if ($LASTEXITCODE -ne 0) { throw "Unable to update rollback state" }
    $state = $stateJson | ConvertFrom-Json
    & docker compose --env-file $envPath -f $composePath exec -T gateway `
        caddy reload --config /etc/caddy/Caddyfile
    if ($LASTEXITCODE -ne 0) { throw "Gateway reload failed during rollback" }
    & $python -m scripts.phase6_release observe --url "$GatewayUrl/api/v1/health/ready" `
        --expected-slot $state.active_slot --requests 10 `
        --output (Join-Path $evidencePath "$releaseId-observation.json")
    if ($LASTEXITCODE -ne 0) { throw "Rollback target did not become healthy" }
    if ($DrainSeconds -gt 0) { Start-Sleep -Seconds $DrainSeconds }
    Write-Output "Rollback accepted: active slot $($state.active_slot); operator $Operator"
}
finally {
    Pop-Location
}

