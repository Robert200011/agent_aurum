param(
    [switch]$Force,
    [switch]$RotateAuthSecrets
)

$projectRoot = Split-Path -Parent $PSScriptRoot
$templatePath = Join-Path $projectRoot ".env.example"
$targetPath = Join-Path $projectRoot ".env"

if ($Force -and $RotateAuthSecrets) {
    throw "-Force and -RotateAuthSecrets cannot be used together."
}
if ($RotateAuthSecrets -and -not (Test-Path -LiteralPath $targetPath)) {
    throw ".env does not exist. Run this script without options to create it."
}
if ((Test-Path -LiteralPath $targetPath) -and -not $Force -and -not $RotateAuthSecrets) {
    throw ".env already exists. Back it up first, or use -Force to overwrite it."
}

function New-RandomToken {
    param([int]$ByteCount)

    $bytes = New-Object byte[] $ByteCount
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($bytes)
    }
    finally {
        $generator.Dispose()
    }

    return [Convert]::ToBase64String($bytes).TrimEnd("=").Replace("+", "-").Replace("/", "_")
}

function Set-EnvironmentValue {
    param(
        [string]$Content,
        [string]$Name,
        [string]$Value
    )

    $pattern = [regex]::new("(?m)^$([regex]::Escape($Name))=.*$")
    if (-not $pattern.IsMatch($Content)) {
        throw "Missing configuration entry in template: $Name"
    }
    return $pattern.Replace($Content, "$Name=$Value", 1)
}

$postgresPassword = New-RandomToken -ByteCount 24
$appDatabasePassword = New-RandomToken -ByteCount 24
$jwtSecret = New-RandomToken -ByteCount 48
$minioRootUser = "aurum-root"
$minioRootPassword = New-RandomToken -ByteCount 32
$objectStorageAccessKey = "aurum-app"
$objectStorageSecretKey = New-RandomToken -ByteCount 32

$sourcePath = if ($RotateAuthSecrets) { $targetPath } else { $templatePath }
$content = Get-Content -LiteralPath $sourcePath -Raw -Encoding utf8
$content = Set-EnvironmentValue $content "AURUM_JWT_SECRET_KEY" $jwtSecret

if ($RotateAuthSecrets) {
    Set-Content -LiteralPath $targetPath -Value $content -Encoding utf8
    Write-Output "Rotated the JWT signing secret in .env."
    Write-Output "Existing access and refresh tokens are now invalid."
    exit 0
}

$content = Set-EnvironmentValue $content "POSTGRES_PASSWORD" $postgresPassword
$content = Set-EnvironmentValue $content "AURUM_APP_DB_PASSWORD" $appDatabasePassword
$content = Set-EnvironmentValue $content "MINIO_ROOT_USER" $minioRootUser
$content = Set-EnvironmentValue $content "MINIO_ROOT_PASSWORD" $minioRootPassword
$content = Set-EnvironmentValue $content "AURUM_OBJECT_STORAGE_ACCESS_KEY" $objectStorageAccessKey
$content = Set-EnvironmentValue $content "AURUM_OBJECT_STORAGE_SECRET_KEY" $objectStorageSecretKey
$content = Set-EnvironmentValue $content "AURUM_DATABASE_URL" (
    "postgresql+asyncpg://aurum_app:${appDatabasePassword}@localhost:5432/aurum"
)
$content = Set-EnvironmentValue $content "AURUM_MIGRATION_DATABASE_URL" (
    "postgresql+asyncpg://aurum:${postgresPassword}@localhost:5432/aurum"
)
Set-Content -LiteralPath $targetPath -Value $content -Encoding utf8
Write-Output "Generated .env with secrets stored only on this machine."
