$ErrorActionPreference = 'Stop'

$taskName = 'AuraDrones_DailyFactory'
$factoryDir = 'C:\Users\aldo_\Desktop\videos-ia\_shared\factory'
$scriptPath = Join-Path $factoryDir 'fabrica_diaria.py'
$weeklyTaskName = 'AuraDrones_WeeklyUpgradeRadar'
$weeklyScriptPath = Join-Path $factoryDir 'weekly_upgrade_radar.py'

if (-not (Test-Path -LiteralPath $scriptPath)) {
    throw "No existe $scriptPath"
}
if (-not (Test-Path -LiteralPath $weeklyScriptPath)) {
    throw "No existe $weeklyScriptPath"
}

$pythonCommand = Get-Command python -ErrorAction Stop
$pythonPath = $pythonCommand.Source
$pythonwPath = Join-Path (Split-Path -Path $pythonPath -Parent) 'pythonw.exe'
$executable = if (Test-Path -LiteralPath $pythonwPath) { $pythonwPath } else { $pythonPath }

$action = New-ScheduledTaskAction -Execute $executable -Argument ('"{0}"' -f $scriptPath) -WorkingDirectory $factoryDir
$trigger = New-ScheduledTaskTrigger -Daily -At '22:00'
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -Hidden -ExecutionTimeLimit (New-TimeSpan -Hours 8)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
Write-Output "Tarea '$taskName' registrada diariamente a las 22:00: $executable $scriptPath"

$weeklyAction = New-ScheduledTaskAction -Execute $executable -Argument ('"{0}"' -f $weeklyScriptPath) -WorkingDirectory $factoryDir
$weeklyTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At '11:00'
$weeklySettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -Hidden -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask -TaskName $weeklyTaskName -Action $weeklyAction -Trigger $weeklyTrigger -Settings $weeklySettings -Principal $principal -Force | Out-Null
Write-Output "Tarea '$weeklyTaskName' registrada domingos a las 11:00: $executable $weeklyScriptPath"
