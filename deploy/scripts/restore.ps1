[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Backup,
    [Parameter(Mandatory = $true)][string]$DestinationDatabase,
    [Parameter(Mandatory = $true)][string]$DestinationBucket,
    [Parameter(Mandatory = $true)][string]$Report,
    [switch]$ConfirmNewTargets,
    [string]$EnvFile = ".env"
)

$ErrorActionPreference = "Stop"
if (-not $ConfirmNewTargets) {
    throw "Restore only supports new isolated targets; pass -ConfirmNewTargets after review."
}
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$python = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
Push-Location $repositoryRoot
try {
    & $python -m scripts.phase6_backup --env-file $EnvFile restore `
        --backup $Backup --destination-database $DestinationDatabase `
        --destination-bucket $DestinationBucket --report $Report --confirm-new-targets
    if ($LASTEXITCODE -ne 0) { throw "Restore failed with exit code $LASTEXITCODE" }
}
finally {
    Pop-Location
}

