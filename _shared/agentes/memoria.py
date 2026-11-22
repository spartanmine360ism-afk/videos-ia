from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
SHARED = ROOT / "_shared"
CACHE = SHARED / "cache" / "agentes"
PAQUETES_PERMITIDOS = {
    "playwright": "playwright",
    "psutil": "psutil",
    "rapidocr-onnxruntime": "rapidocr_onnxruntime",
    "requests": "requests",
    "edge-tts": "edge_tts",
}


def hash_canonico(datos: Any) -> str:
    texto = json.dumps(datos, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def leer_json(ruta: Path | str, defecto: Any = None) -> Any:
    ruta = Path(ruta)
    try:
        return json.loads(ruta.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return defecto


def escribir_json(ruta: Path | str, datos: Any) -> Path:
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_name(ruta.name + ".tmp")
    texto = json.dumps(datos, ensure_ascii=False, indent=2, default=str) + "\n"
    temporal.write_text(texto, encoding="utf-8")
    temporal.replace(ruta)
    return ruta


def escribir_texto(ruta: Path | str, contenido: str) -> Path:
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_name(ruta.name + ".tmp")
    temporal.write_text(contenido, encoding="utf-8")
    temporal.replace(ruta)
    return ruta


def cache_json(
    namespace: str,
    clave: Any,
    productor: Callable[[], Any],
    ttl_s: int | None = None,
) -> Any:
    ruta = CACHE / namespace / (hash_canonico(clave) + ".json")
    if ruta.is_file():
        if ttl_s is None or time.time() - ruta.stat().st_mtime <= ttl_s:
            return leer_json(ruta)
    datos = productor()
    escribir_json(ruta, datos)
    return datos


def sha256_archivo(ruta: Path | str) -> str:
    ruta = Path(ruta)
    digest = hashlib.sha256()
    with ruta.open("rb") as archivo:
        for bloque in iter(lambda: archivo.read(1024 * 1024), b""):
            digest.update(bloque)
    return digest.hexdigest()


def clave_archivos(proyecto: Path | str, archivos: list[str]) -> dict[str, Any]:
    proyecto = Path(proyecto)
    lista = []
    for relativo in archivos:
        ruta = proyecto / relativo
        if ruta.is_file():
            lista.append(
                {
                    "archivo": relativo,
                    "tamano": ruta.stat().st_size,
                    "sha256": sha256_archivo(ruta),
                }
            )
        else:
            lista.append({"archivo": relativo, "ausente": True})
    return {"proyecto": str(proyecto.name), "archivos": lista}


def cache_video(
    namespace: str,
    clave: Any,
    productor: Callable[[Path], Path | str],
    extension: str = ".mp4",
) -> tuple[Path, bool]:
    ruta = CACHE / namespace / (hash_canonico(clave) + extension)
    if ruta.is_file() and ruta.stat().st_size > 0:
        return ruta, True
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_name(ruta.name + ".tmp" + extension)
    try:
        if temporal.exists():
            temporal.unlink()
        generado = Path(productor(temporal))
        if not generado.is_file() or generado.stat().st_size == 0:
            raise OSError(f"El productor no generó un video válido: {generado}")
        shutil.copy2(generado, temporal)
        temporal.replace(ruta)
    except Exception:
        if temporal.exists():
            temporal.unlink(missing_ok=True)
        raise
    return ruta, False


def buscar_binario(nombre: str) -> str:
    encontrado = shutil.which(nombre)
    if encontrado:
        return encontrado
    alternativas = [
        Path("C:/ffmpeg/bin") / (nombre + ".exe"),
        Path("C:/Program Files/ffmpeg/bin") / (nombre + ".exe"),
    ]
    for alternativa in alternativas:
        if alternativa.is_file():
            return str(alternativa)
    return ""


def asegurar_paquete(nombre: str, import_name: str | None = None) -> dict[str, Any]:
    if nombre not in PAQUETES_PERMITIDOS:
        return {"paquete": nombre, "estado": "bloqueado", "detalle": "Fuera de la lista permitida"}
    modulo = import_name or PAQUETES_PERMITIDOS[nombre]
    try:
        existe = importlib.util.find_spec(modulo) is not None
    except (ImportError, ValueError):
        existe = False
    if existe:
        return {"paquete": nombre, "estado": "ya_disponible", "detalle": modulo}
    if os.getenv("AURA_AUTO_INSTALL", "1") != "1":
        return {"paquete": nombre, "estado": "pendiente", "detalle": "AURA_AUTO_INSTALL=0"}
    try:
        visible = subprocess.run(
            [sys.executable, "-m", "pip", "show", nombre],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if visible.returncode != 0:
            instalacion = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--index-url",
                    "https://pypi.org/simple",
                    "--disable-pip-version-check",
                    "--no-input",
                    "--timeout",
                    "15",
                    nombre,
                ],
                capture_output=True,
                text=True,
                timeout=900,
            )
            if instalacion.returncode != 0:
                return {
                    "paquete": nombre,
                    "estado": "fallo",
                    "detalle": instalacion.stderr.strip()[-500:],
                }
        verificacion = subprocess.run(
            [sys.executable, "-m", "pip", "check"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        return {
            "paquete": nombre,
            "estado": "instalado" if verificacion.returncode == 0 else "instalado_con_aviso",
            "detalle": verificacion.stdout.strip()[-300:] or verificacion.stderr.strip()[-300:],
        }
    except Exception as error:
        return {"paquete": nombre, "estado": "fallo", "detalle": f"{type(error).__name__}: {error}"}


def asegurar_paquetes(nombres: list[str]) -> list[dict[str, Any]]:
    return [asegurar_paquete(nombre) for nombre in nombres]


def perfil_hardware() -> dict[str, Any]:
    cpu = os.cpu_count() or 4
    ram_gb = 0.0
    try:
        import psutil

        ram_gb = round(psutil.virtual_memory().total / (1024**3), 1)
    except Exception:
        ram_gb = 0.0
    gpu = "no_detectada"
    try:
        smsi = shutil.which("nvidia-smi")
        if smsi:
            proceso = subprocess.run(
                [smsi, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if proceso.returncode == 0 and proceso.stdout.strip():
                gpu = proceso.stdout.strip().splitlines()[0]
    except Exception:
        pass
    if cpu <= 4 or (ram_gb and ram_gb < 8):
        perfil = "bajo"
        workers = 1
        calidad = "draft"
    elif cpu <= 8 or (ram_gb and ram_gb < 16):
        perfil = "medio"
        workers = 2
        calidad = "estandar"
    else:
        perfil = "alto"
        workers = min(4, max(2, cpu // 4))
        calidad = "estandar"
    return {
        "cpu_logicos": cpu,
        "ram_gb": ram_gb,
        "gpu": gpu,
        "perfil": perfil,
        "workers": workers,
        "calidad": calidad,
        "ffmpeg": buscar_binario("ffmpeg"),
        "ffprobe": buscar_binario("ffprobe"),
        "actualizado_en": datetime.now().isoformat(timespec="seconds"),
    }
