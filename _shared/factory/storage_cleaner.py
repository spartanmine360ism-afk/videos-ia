from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT_DIR = Path(__file__).resolve().parents[2]
FACTORY_DIR = Path(__file__).resolve().parent
QUEUE_PATH = ROOT_DIR / "_shared" / "publisher" / "schedule_queue.json"
LOG_PATH = FACTORY_DIR / "factory.log"
HORAS = 48
DIRECTORIOS_TEMPORARIOS = {
    "node_modules",
    ".hyperframes",
    "frames",
    "frames_temp",
    "temp",
    "tmp",
    "temporal",
    "temporales",
    "cache",
}
PREFIJOS_TEMPORARIOS = ("frame_", "frames_", "tmp_", "temp_")

if str(FACTORY_DIR) not in sys.path:
    sys.path.insert(0, str(FACTORY_DIR))

import housekeeping


def log(mensaje: str) -> None:
    sello = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")
    linea = f"[{sello}] [STORAGE] {mensaje}"
    print(linea)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as archivo:
        archivo.write(linea + "\n")


def tamano(ruta: Path) -> int:
    if ruta.is_symlink() or not ruta.exists():
        return 0
    if ruta.is_file():
        try:
            return ruta.stat().st_size
        except OSError:
            return 0
    total = 0
    try:
        for entry in ruta.rglob("*"):
            if entry.is_file() and not entry.is_symlink():
                try:
                    total += entry.stat().st_size
                except OSError:
                    pass
    except OSError:
        return 0
    return total


def es_temporal(ruta: Path) -> bool:
    nombre = ruta.name.casefold()
    return nombre in DIRECTORIOS_TEMPORARIOS or nombre.startswith(PREFIJOS_TEMPORARIOS)


def archivos_protegidos(proyecto: Path) -> set[Path]:
    protegidos: set[Path] = set()
    for metadata in proyecto.rglob("metadata.json"):
        if metadata.is_file() and not metadata.is_symlink():
            protegidos.add(metadata.resolve())
    renders = proyecto / "renders"
    final = housekeeping.video_final(renders)
    if final is not None and final.is_file():
        protegidos.add(final.resolve())
    for nombre in ("portada.jpg", "portada_youtube.jpg", "portada_tiktok.jpg", "portada_instagram.jpg", "portada_facebook.jpg", "cover.jpg"):
        pth = renders / nombre
        if pth.is_file():
            protegidos.add(pth.resolve())
    return protegidos


def borrar(ruta: Path, dry_run: bool) -> int:
    liberado = tamano(ruta)
    if not dry_run:
        try:
            if ruta.is_dir() and not ruta.is_symlink():
                shutil.rmtree(ruta)
            else:
                ruta.unlink()
        except OSError:
            return 0
    return liberado


def limpiar_proyecto(proyecto: Path, dry_run: bool = False) -> tuple[int, int]:
    protegidos = archivos_protegidos(proyecto)
    if not any(ruta.name.endswith(".mp4") for ruta in protegidos):
        return 0, 0

    liberado = 0
    eliminados = 0
    for ruta in list(proyecto.rglob("*")):
        if ruta.is_symlink() or ruta.resolve() in protegidos:
            continue
        if ruta.is_dir() and es_temporal(ruta):
            ganado = borrar(ruta, dry_run)
            if ganado or not dry_run:
                liberado += ganado
                eliminados += 1
            continue
        if ruta.is_file():
            liberado += borrar(ruta, dry_run)
            eliminados += 1

    for directorio in sorted(
        (ruta for ruta in proyecto.rglob("*") if ruta.is_dir() and not ruta.is_symlink()),
        key=lambda ruta: len(ruta.parts),
        reverse=True,
    ):
        if not dry_run:
            try:
                directorio.rmdir()
            except OSError:
                pass
    return eliminados, liberado


def limpiar(horas: int = HORAS, dry_run: bool = False) -> dict[str, Any]:
    if not QUEUE_PATH.is_file():
        return {"proyectos": 0, "eliminados": 0, "liberado_bytes": 0}

    try:
        datos = json.loads(QUEUE_PATH.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError) as error:
        log(f"No se pudo leer schedule_queue.json: {error}")
        return {"proyectos": 0, "eliminados": 0, "liberado_bytes": 0}

    limite = datetime.now(timezone.utc) - timedelta(hours=max(1, horas))
    candidatos: dict[Path, str] = {}
    for tarea in datos.get("tareas", []):
        if not isinstance(tarea, dict):
            continue
        fecha = housekeeping.fecha_publicacion(tarea)
        if fecha is None or fecha > limite:
            continue
        proyecto = housekeeping.resolver_proyecto(tarea)
        if proyecto is None or not proyecto.is_relative_to(ROOT_DIR) or "_shared" in proyecto.parts:
            continue
        candidatos.setdefault(proyecto, fecha.isoformat())

    total_eliminados = 0
    total_liberado = 0
    omitidos: list[str] = []
    for proyecto, fecha in candidatos.items():
        eliminados, liberado = limpiar_proyecto(proyecto, dry_run)
        if not eliminados and not liberado:
            omitidos.append(proyecto.name)
            continue
        total_eliminados += eliminados
        total_liberado += liberado
        log(
            f"{'DRY-RUN ' if dry_run else ''}{proyecto.name}: publicado {fecha}, "
            f"{eliminados} temporales, {liberado / (1024 * 1024):.1f} MB liberados"
        )

    return {
        "proyectos": len(candidatos),
        "eliminados": total_eliminados,
        "liberado_bytes": total_liberado,
        "liberado_mb": round(total_liberado / (1024 * 1024), 2),
        "omitidos": omitidos,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Limpia temporales de proyectos publicados hace más de 48 horas.")
    parser.add_argument("--dry-run", action="store_true", help="Muestra qué se borraría sin eliminar")
    parser.add_argument("--horas", type=int, default=HORAS, help="Antigüedad mínima en horas")
    args = parser.parse_args(argv)
    print(json.dumps(limpiar(max(1, args.horas), args.dry_run), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
