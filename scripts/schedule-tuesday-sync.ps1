# Run once in Windows PowerShell on your home PC.
# Registers a weekly 10 PM LOCAL Windows time refresh (Tuesday).
# Windows should be configured to Pacific Time so daylight saving is handled.
$ErrorActionPreference = "Stop"
$project = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$privateRepo = Join-Path $HOME "Documents\yahoo-fantasy-private-data"
$publisher = Join-Path $project "scripts\publish-private-yahoo.ps1"
if (-not (Test-Path (Join-Path $privateRepo ".git"))) { throw "Private repository clone not found at $privateRepo" }
if (-not (Test-Path $publisher)) { throw "Publisher missing at $publisher" }
$zone = (Get-TimeZone).Id
if ($zone -notin @("Pacific Standard Time", "America/Los_Angeles")) {
    throw "Windows timezone is '$zone'. Set Windows time zone to Pacific Time before scheduling 10 PM PT."
}
$command = "-NoProfile -ExecutionPolicy Bypass -File `"$publisher`" -PrivateRepoPath `"$privateRepo`""
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $command -WorkingDirectory $project
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Tuesday -At "22:00"
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2)
# Current user, interactive token; no password stored and no administrator required.
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName "Yahoo Fantasy Private Sync - Tuesday" -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
Write-Host "Registered Tuesday 10:00 PM Pacific task. Requires this Windows account to be signed in, machine awake, internet, and valid Yahoo/GitHub authentication."
Write-Host "Check: Get-ScheduledTask -TaskName 'Yahoo Fantasy Private Sync - Tuesday' | Get-ScheduledTaskInfo"
