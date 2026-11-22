from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT_DIR = Path(__file__).resolve().parents[2]
VAULT_DIR = ROOT_DIR / "_shared" / "media_vault"
INDEX_PATH = VAULT_DIR / "index.json"
VAULT_INDEX_JSON = VAULT_DIR / "vault_index.json"
CARPETAS = ("fpv", "cine", "dji", "general")
ALIAS = {
    "avata_fpv": "fpv",
    "cinematico": "cine",
    "urbano": "general",
    "gadgets": "dji",
    "dji_mini3": "dji",
    "tomas_urbanas": "general",
    "broll_general": "general",
}
EXTENSIONES = ("*.mp4", "*.mov")


def ruta_ffprobe() -> str:
    return str(os.getenv("FFPROBE_BIN") or shutil.which("ffprobe") or "ffprobe")


def fecha_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def categoria_de(ruta: Path) -> str:
    nombre = ruta.stem.casefold()
    carpeta = ruta.parent.name.casefold()
    for cat in CARPETAS:
        if cat in nombre or cat in carpeta:
            return cat
    return ALIAS.get(carpeta, carpeta if carpeta in CARPETAS else "general")


def sonda(ruta: Path) -> dict[str, Any]:
    comando = [
        ruta_ffprobe(),
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=codec_name,width,height,codec_type",
        "-of",
        "json",
        str(ruta),
    ]
    resultado = subprocess.run(comando, text=True, capture_output=True)
    if resultado.returncode != 0:
        raise RuntimeError((resultado.stderr or resultado.stdout).strip() or "ffprobe falló")
    datos = json.loads(resultado.stdout or "{}")
    video = next(
        (stream for stream in datos.get("streams", []) if stream.get("codec_type") == "video"),
        {},
    )
    ancho = int(video.get("width") or 0)
    alto = int(video.get("height") or 0)
    try:
        duracion = round(float(datos.get("format", {}).get("duration") or 0), 2)
    except (TypeError, ValueError):
        duracion = 0.0
    return {
        "duracion_s": duracion,
        "ancho": ancho,
        "alto": alto,
        "resolucion": f"{ancho}x{alto}" if ancho and alto else "desconocida",
        "codec": str(video.get("codec_name") or "desconocido"),
        "es_vertical": alto > ancho > 0,
    }


def indexar(raiz: Path | None = None, salida: Path | None = None, escribir: bool = True) -> dict[str, Any]:
    raiz = (raiz or VAULT_DIR).resolve()
    salida = (salida or (raiz / "index.json")).resolve()
    clips: list[dict[str, Any]] = []
    errores: list[str] = []

    carpetas = list(CARPETAS) + list(ALIAS)
    for nombre in carpetas:
        carpeta = raiz / nombre
        if not carpeta.is_dir():
            continue
        for extension in EXTENSIONES:
            for archivo in sorted(carpeta.rglob(extension)):
                if not archivo.is_file() or archivo.name.startswith("."):
                    continue
                try:
                    datos = sonda(archivo)
                except Exception as error:
                    errores.append(f"{archivo.relative_to(raiz).as_posix()}: {type(error).__name__}: {error}")
                    continue
                try:
                    bytes_archivo = archivo.stat().st_size
                except OSError:
                    bytes_archivo = 0
                clips.append(
                    {
                        "carpeta": categoria_de(archivo),
                        "carpeta_origen": carpeta.name,
                        "archivo": archivo.name,
                        "ruta": archivo.relative_to(ROOT_DIR).as_posix(),
                        "ruta_absoluta": str(archivo),
                        "tamano_bytes": bytes_archivo,
                        "tamano_mb": round(bytes_archivo / (1024 * 1024), 2),
                        "modificado_en": datetime.fromtimestamp(archivo.stat().st_mtime, timezone.utc)
                        .replace(microsecond=0)
                        .isoformat()
                        .replace("+00:00", "Z"),
                        **datos,
                    }
                )

    vistos: set[str] = set()
    unicos: list[dict[str, Any]] = []
    for clip in clips:
        if clip["ruta"] in vistos:
            continue
        vistos.add(clip["ruta"])
        unicos.append(clip)
    unicos.sort(key=lambda clip: (clip["carpeta"], clip["archivo"].casefold()))

    por_carpeta: dict[str, int] = {nombre: 0 for nombre in CARPETAS}
    for clip in unicos:
        por_carpeta[clip["carpeta"]] = por_carpeta.get(clip["carpeta"], 0) + 1

    resultado = {
        "generado_en": fecha_iso(),
        "raiz": str(raiz),
        "total_clips": len(unicos),
        "por_carpeta": por_carpeta,
        "clips": unicos,
        "errores": errores[:20],
    }
    if escribir:
        salida.parent.mkdir(parents=True, exist_ok=True)
        contenido = json.dumps(resultado, ensure_ascii=False, indent=2) + "\n"
        for target in (salida, VAULT_INDEX_JSON.resolve()):
            temporal = target.with_name(target.name + ".tmp")
            temporal.write_text(contenido, encoding="utf-8")
            temporal.replace(target)
    return resultado


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Indexa clips reales de la bóveda con duración y resolución.")
    parser.add_argument("--raiz", default=str(VAULT_DIR), help="Carpeta de la bóveda")
    parser.add_argument("--salida", default=str(INDEX_PATH), help="Ruta del index.json")
    parser.add_argument("--dry-run", action="store_true", help="No escribe el índice")
    args = parser.parse_args(argv)

    try:
        resultado = indexar(Path(args.raiz), Path(args.salida), escribir=not args.dry_run)
    except OSError as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 2

    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
