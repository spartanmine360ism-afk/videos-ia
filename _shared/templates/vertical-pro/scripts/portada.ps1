param([string]$Proyecto = (Get-Location).Path)

$renders = Join-Path $Proyecto "renders"
$mp4 = Get-ChildItem -Path $renders -Filter "*.mp4" -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $mp4) {
  throw "No hay MP4 en $renders"
}

$destino = Join-Path $renders "portada.jpg"
& ffmpeg -y -ss 2 -i $mp4.FullName -frames:v 1 -update 1 -q:v 2 $destino
if ($LASTEXITCODE -ne 0) {
  throw "ffmpeg falló al extraer portada.jpg"
}

$destino
