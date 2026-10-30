param([string]$PythonPath)
$ErrorActionPreference = 'Stop'
$project = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (!$PythonPath) { $PythonPath = Join-Path $project '.venv\Scripts\python.exe' }
if (!(Test-Path -LiteralPath $PythonPath)) { throw 'Python environment missing.' }
if ((Get-TimeZone).Id -notin @('Pacific Standard Time', 'America/Los_Angeles')) { throw 'Windows timezone must be Pacific.' }
$publisher = Join-Path $project 'scripts\publish-private-yahoo.ps1'
$command = "-NoProfile -File `"$publisher`" -PythonPath `"$PythonPath`""
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $command -WorkingDirectory $project
$triggers = @((New-ScheduledTaskTrigger -Daily -At '07:00'), (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Tuesday -At '22:00'))
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun -MultipleInstances IgnoreNew -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 10) -ExecutionTimeLimit (New-TimeSpan -Hours 2)
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'Yahoo Fantasy Private Sync - Tuesday' -Action $action -Trigger $triggers -Settings $settings -Principal $principal -Force | Out-Null
Write-Host 'Registered daily 7 AM and Tuesday 10 PM Pacific sync. Requires signed-in account, network, and valid Yahoo/GitHub authorization.'
