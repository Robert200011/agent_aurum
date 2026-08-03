[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$TaskName = "AurumAgentDailyBackup",
    [string]$OutputDirectory = "C:\AurumBackups\primary",
    [string]$ReplicaDirectory = "D:\AurumBackups\replica",
    [string]$DailyAt = "02:00"
)

$ErrorActionPreference = "Stop"
$backupScript = (Resolve-Path (Join-Path $PSScriptRoot "backup.ps1")).Path
$arguments = "-NoProfile -NonInteractive -File `"$backupScript`" " +
    "-OutputDirectory `"$OutputDirectory`" -ReplicaDirectory `"$ReplicaDirectory`""
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arguments
$trigger = New-ScheduledTaskTrigger -Daily -At $DailyAt
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 4)
if ($PSCmdlet.ShouldProcess($TaskName, "register daily encrypted backup task")) {
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
        -Settings $settings -Description "Aurum Agent P6.4 encrypted daily backup" -Force
}

