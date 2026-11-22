param(
  [string]$Proyecto = ".",
  [string]$Voz = "assets/audio/voz.mp3",
  [string]$Musica = "assets/audio/musica.mp3",
  [string[]]$Sfx = @(),
  [double]$VolumenMusica = 0.12,
  [double]$VolumenSfx = 0.35,
  [string]$Categoria = "",
  [switch]$SinDucking
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
  throw "ffmpeg no está disponible en PATH."
}

$raiz = (Resolve-Path -LiteralPath $Proyecto).Path
$directorScript = Split-Path -Parent $MyInvocation.MyCommand.Path
$sfxCompartidos = Join-Path (Split-Path -Parent $directorScript) "sfx"
$carpetaAudio = Join-Path $raiz "assets\audio"
New-Item -ItemType Directory -Force -Path $carpetaAudio | Out-Null

function Resolve-ProyectoPath([string]$ruta) {
  if ([System.IO.Path]::IsPathRooted($ruta)) {
    return $ruta
  }
  return (Join-Path $raiz $ruta)
}

function Get-LoudnormStats([string]$archivo) {
  $preferenciaAnterior = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    $salida = & ffmpeg -hide_banner -nostats -i $archivo -af "loudnorm=I=-14:TP=-1:LRA=11:print_format=json" -f null - 2>&1 | Out-String
  } finally {
    $ErrorActionPreference = $preferenciaAnterior
  }
  $inicio = $salida.IndexOf("{")
  $fin = $salida.LastIndexOf("}")
  if ($inicio -lt 0 -or $fin -le $inicio) {
    return $null
  }
  try {
    return ($salida.Substring($inicio, $fin - $inicio + 1) | ConvertFrom-Json)
  } catch {
    return $null
  }
}

function Invoke-FFmpeg([string[]]$argumentos, [string]$mensaje) {
  & ffmpeg @argumentos
  if ($LASTEXITCODE -ne 0) {
    throw $mensaje
  }
}

function Get-IntegratedLoudness([string]$archivo) {
  $stats = Get-LoudnormStats $archivo
  if (-not $stats -or -not $stats.input_i) {
    return $null
  }
  try {
    return [double]::Parse($stats.input_i, [System.Globalization.CultureInfo]::InvariantCulture)
  } catch {
    return $null
  }
}

$vozPath = Resolve-ProyectoPath $Voz
if (-not (Test-Path -LiteralPath $vozPath)) {
  throw "No existe la voz: $vozPath"
}

$rutaMusica = $Musica
if (-not $SinDucking -and -not $PSBoundParameters.ContainsKey('Musica')) {
  $mezcladorPython = Join-Path $directorScript "..\factory\audio_mixer.py"
  $pythonExe = $env:AURA_PYTHON
  if (-not $pythonExe) {
    $comandoPython = Get-Command python -ErrorAction SilentlyContinue
    if ($comandoPython) { $pythonExe = $comandoPython.Source }
  }
  if ($pythonExe -and (Test-Path -LiteralPath $mezcladorPython)) {
    $salidaMezclador = Join-Path $carpetaAudio "musica_duck.wav"
    $informacion = & $pythonExe $mezcladorPython --proyecto $raiz --categoria $Categoria --voz $Voz --salida $salidaMezclador --volumen $VolumenMusica 2>$null | Out-String
    if ($LASTEXITCODE -eq 0 -and (Test-Path -LiteralPath $salidaMezclador)) {
      $rutaMusica = $salidaMezclador
      $SinDucking = $true
      if ($informacion.Trim()) { Write-Output "MUSICA_ADAPTATIVA: $($informacion.Trim())" }
    }
  }
}

$musicaPath = Resolve-ProyectoPath $rutaMusica
$vozNorm = Join-Path $carpetaAudio "voz_norm.wav"
$musicaDuck = Join-Path $carpetaAudio "musica_duck.wav"
$preview = Join-Path $carpetaAudio "mezcla_preview.wav"
$volMusica = $VolumenMusica.ToString([System.Globalization.CultureInfo]::InvariantCulture)
$volSfx = $VolumenSfx.ToString([System.Globalization.CultureInfo]::InvariantCulture)

$medidaInicial = Get-IntegratedLoudness $vozPath
if ($null -eq $medidaInicial) {
  Invoke-FFmpeg @("-y", "-hide_banner", "-loglevel", "error", "-i", $vozPath, "-af", "loudnorm=I=-14:TP=-1:LRA=11", "-ar", "48000", "-c:a", "pcm_s16le", $vozNorm) "Falló la normalización de voz."
} else {
  $ganancia = -14 - $medidaInicial
  for ($intento = 0; $intento -lt 4; $intento++) {
    $ganancia = [Math]::Min(24, [Math]::Max(-24, $ganancia))
    $gananciaTexto = $ganancia.ToString("0.##", [System.Globalization.CultureInfo]::InvariantCulture)
    $filtroVoz = 'highpass=f=80,volume={0}dB,alimiter=limit=0.891:level=false' -f $gananciaTexto
    Invoke-FFmpeg @("-y", "-hide_banner", "-loglevel", "error", "-i", $vozPath, "-af", $filtroVoz, "-ar", "48000", "-c:a", "pcm_s16le", $vozNorm) "Falló la normalización de voz."
    $medida = Get-IntegratedLoudness $vozNorm
    if ($null -eq $medida) {
      break
    }
    $diferencia = -14 - $medida
    if ([Math]::Abs($diferencia) -le 0.2) {
      break
    }
    $ganancia += $diferencia
  }
}

if (Test-Path -LiteralPath $musicaPath) {
  if ($SinDucking) {
    if ([System.IO.Path]::GetFullPath($musicaPath) -ine [System.IO.Path]::GetFullPath($musicaDuck)) {
      Copy-Item -LiteralPath $musicaPath -Destination $musicaDuck -Force
    }
  } else {
    $filtroDuck = ('[1:a]volume={0}[base];[base][0:a]sidechaincompress=threshold=0.02:ratio=8:attack=20:release=350:makeup=1[duck]' -f $volMusica)
    Invoke-FFmpeg @("-y", "-hide_banner", "-loglevel", "error", "-i", $vozNorm, "-i", $musicaPath, "-filter_complex", $filtroDuck, "-map", "[duck]", "-ar", "48000", "-c:a", "pcm_s16le", $musicaDuck) "Falló el ducking de música."
  }
} else {
  Write-Warning "Sin música en $musicaPath; se omite ducking."
  Remove-Item -LiteralPath $musicaDuck -Force -ErrorAction SilentlyContinue
}

$argumentosPreview = @("-y", "-hide_banner", "-loglevel", "error", "-i", $vozNorm)
$filtros = New-Object System.Collections.Generic.List[string]
$lanes = New-Object System.Collections.Generic.List[string]
$lanes.Add("[0:a]")
$indice = 1
$numeroSfx = 0

if (Test-Path -LiteralPath $musicaDuck) {
  $argumentosPreview += @("-i", $musicaDuck)
  $lanes.Add(('[{0}:a]' -f $indice))
  $indice++
}

foreach ($entrada in $Sfx) {
  $partes = $entrada -split "@", 2
  $archivoSfx = $partes[0]
  $segundos = if ($partes.Count -gt 1) { [double]::Parse($partes[1], [System.Globalization.CultureInfo]::InvariantCulture) } else { 0 }
  $rutaSfx = Resolve-ProyectoPath $archivoSfx
  if (-not (Test-Path -LiteralPath $rutaSfx)) {
    $rutaSfx = Join-Path $sfxCompartidos $archivoSfx
  }
  if (-not (Test-Path -LiteralPath $rutaSfx)) {
    Write-Warning "SFX no encontrado: $archivoSfx"
    continue
  }
  $milisegundos = [int][Math]::Round($segundos * 1000)
  $argumentosPreview += @("-i", $rutaSfx)
  $filtros.Add(('[{0}:a]aformat=channel_layouts=stereo,adelay={1}|{1},volume={2}[sfx{3}]' -f $indice, $milisegundos, $volSfx, $numeroSfx))
  $lanes.Add(('[sfx{0}]' -f $numeroSfx))
  $indice++
  $numeroSfx++
}

$filtroMezcla = ($lanes -join "") + ('amix=inputs={0}:duration=first:dropout_transition=0:normalize=0[out]' -f $lanes.Count)
$todosLosFiltros = @($filtros.ToArray()) + $filtroMezcla
$argumentosPreview += @("-filter_complex", ($todosLosFiltros -join ";"), "-map", "[out]", "-ar", "48000", "-c:a", "pcm_s16le", $preview)
Invoke-FFmpeg $argumentosPreview "Falló la mezcla de previsualización."

Write-Output "VOZ=-14 LUFS: $vozNorm"
if (Test-Path -LiteralPath $musicaDuck) {
  Write-Output "MUSICA_DUCKED: $musicaDuck"
}
Write-Output "PREVIEW: $preview"
