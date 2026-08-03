[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$OutputDirectory,
    [string]$ReplicaDirectory,
    [string]$MetricsFile,
    [ValidateRange(1, 3650)][int]$RetentionDays = 30,
    [string]$EnvFile = ".env",
    [string]$ComposeFile = "compose.yaml",
    [string]$PostgresService = "postgres"
)

$ErrorActionPreference = "Stop"
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$python = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Project virtual environment was not found: $python"
}
$arguments = @(
    "-m", "scripts.phase6_backup", "--env-file", $EnvFile,
    "--compose-file", $ComposeFile, "--compose-env-file", $EnvFile,
    "--postgres-service", $PostgresService,
    "backup", "--output-dir", $OutputDirectory, "--retention-days", $RetentionDays
)
if ($ReplicaDirectory) {
    $arguments += @("--replica-directory", $ReplicaDirectory)
}
if ($MetricsFile) {
    $arguments += @("--metrics-file", $MetricsFile)
}
Push-Location $repositoryRoot
try {
    & $python @arguments
    if ($LASTEXITCODE -ne 0) { throw "Backup failed with exit code $LASTEXITCODE" }
}
finally {
    Pop-Location
}
