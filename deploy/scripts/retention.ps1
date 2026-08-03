[CmdletBinding()]
param(
    [switch]$Apply,
    [string]$Operator = $env:USERNAME,
    [string]$EnvFile = ".env"
)

$ErrorActionPreference = "Stop"
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$python = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
$arguments = @("-m", "scripts.run_data_retention", "--env-file", $EnvFile, "--operator", $Operator)
if ($Apply) { $arguments += "--apply" }
Push-Location $repositoryRoot
try {
    & $python @arguments
    if ($LASTEXITCODE -ne 0) { throw "Retention runner failed with exit code $LASTEXITCODE" }
}
finally {
    Pop-Location
}

