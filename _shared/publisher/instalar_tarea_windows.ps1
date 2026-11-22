$ErrorActionPreference = 'Stop'

$taskName = 'AuraDrones_AutoPublisher'
$publisherDir = 'C:\Users\aldo_\Desktop\videos-ia\_shared\publisher'
$scriptPath = Join-Path $publisherDir 'procesar_cola.py'

$pythonCommand = Get-Command python -ErrorAction Stop
$pythonPath = $pythonCommand.Source
$pythonwPath = Join-Path (Split-Path -Path $pythonPath -Parent) 'pythonw.exe'
$executable = if (Test-Path -LiteralPath $pythonwPath) { $pythonwPath } else { $pythonPath }

$action = New-ScheduledTaskAction -Execute $executable -Argument ('"{0}"' -f $scriptPath) -WorkingDirectory $publisherDir
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 10) -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -Hidden -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
Write-Output "Tarea '$taskName' registrada cada 10 minutos: $executable $scriptPath"
