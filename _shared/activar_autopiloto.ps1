$ErrorActionPreference = 'Stop'

$sharedDir = $PSScriptRoot
$rootDir = Split-Path -Parent $sharedDir
$factoryDir = Join-Path $rootDir '_shared\factory'
$publisherDir = Join-Path $rootDir '_shared\publisher'

$pythonCommand = Get-Command python -ErrorAction Stop
$pythonPath = $pythonCommand.Source
$pythonwPath = Join-Path (Split-Path -Path $pythonPath -Parent) 'pythonw.exe'
$executable = if (Test-Path -LiteralPath $pythonwPath) { $pythonwPath } else { $pythonPath }
$usuario = "$env:USERDOMAIN\$env:USERNAME"
$principal = New-ScheduledTaskPrincipal -UserId $usuario -LogonType Interactive -RunLevel Limited

function Register-AuraTask {
    param(
        [string]$Nombre,
        [string]$ScriptPath,
        [string]$DirectorioTrabajo,
        [array]$Disparadores,
        [int]$MinutosLimite
    )

    if (-not (Test-Path -LiteralPath $ScriptPath)) {
        throw "No existe el script: $ScriptPath"
    }

    $accion = New-ScheduledTaskAction -Execute $executable -Argument ('"{0}"' -f $ScriptPath) -WorkingDirectory $DirectorioTrabajo
    $ajustes = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -Hidden -ExecutionTimeLimit (New-TimeSpan -Minutes $MinutosLimite)
    Register-ScheduledTask -TaskName $Nombre -Action $accion -Trigger $Disparadores -Settings $ajustes -Principal $principal -Force | Out-Null
    Write-Output "Tarea '$Nombre' registrada: $executable $ScriptPath"
}

$disparadorPublicador = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 10) -RepetitionDuration (New-TimeSpan -Days 3650)
Register-AuraTask -Nombre 'AuraDrones_AutoPublisher' -ScriptPath (Join-Path $publisherDir 'procesar_cola.py') -DirectorioTrabajo $publisherDir -Disparadores @($disparadorPublicador) -MinutosLimite 5

$disparadorDiario = New-ScheduledTaskTrigger -Daily -At 22:00
$disparadorInicioSesion = New-ScheduledTaskTrigger -AtLogOn -User $usuario
Register-AuraTask -Nombre 'AuraDrones_DailyFactory' -ScriptPath (Join-Path $factoryDir 'autopilot_maestro.py') -DirectorioTrabajo $factoryDir -Disparadores @($disparadorDiario, $disparadorInicioSesion) -MinutosLimite 240

$disparadorSemanal = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 11:00
Register-AuraTask -Nombre 'AuraDrones_WeeklyUpgradeRadar' -ScriptPath (Join-Path $factoryDir 'weekly_upgrade_radar.py') -DirectorioTrabajo $factoryDir -Disparadores @($disparadorSemanal) -MinutosLimite 30

Get-ScheduledTask -TaskName 'AuraDrones_AutoPublisher', 'AuraDrones_DailyFactory', 'AuraDrones_WeeklyUpgradeRadar' | Select-Object TaskName, State | Format-Table -AutoSize
