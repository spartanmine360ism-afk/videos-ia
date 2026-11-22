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
DIAS = 7
ESTADOS_PUBLICADOS = {"published", "scheduled_native", "programado", "publicado"}
ARCHIVOS_PROTEGIDOS = {
    "metadata.json",
    "portada.jpg",
    "portada_youtube.jpg",
    "portada_tiktok.jpg",
    "portada_instagram.jpg",
    "portada_facebook.jpg",
    "cover.jpg",
}


def log(mensaje: str) -> None:
    sello = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")
    linea = f"[{sello}] [HOUSEKEEPING] {mensaje}"
    print(linea)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as archivo:
        archivo.write(linea + "\n")


def parse_fecha(valor: Any) -> datetime | None:
    texto = str(valor or "").strip().replace("Z", "+00:00")
    if not texto:
        return None
    try:
        fecha = datetime.fromisoformat(texto)
    except ValueError:
        return None
    return fecha if fecha.tzinfo else fecha.replace(tzinfo=timezone.utc)


def fecha_publicacion(tarea: dict[str, Any]) -> datetime | None:
    for clave in ("publicado_en", "publicado", "fecha_publicacion"):
        fecha = parse_fecha(tarea.get(clave))
        if fecha is not None:
            return fecha
    estado = str(tarea.get("estado", "")).strip().casefold()
    if estado in ESTADOS_PUBLICADOS:
        return parse_fecha(tarea.get("scheduled_at"))
    return None


def resolver_proyecto(tarea: dict[str, Any]) -> Path | None:
    candidatos: list[Any] = [tarea.get("proyecto"), tarea.get("video")]
    metadata = tarea.get("metadata") if isinstance(tarea.get("metadata"), dict) else {}
    config = tarea.get("config") if isinstance(tarea.get("config"), dict) else {}
    candidatos.extend([metadata.get("proyecto"), config.get("proyecto")])

    for valor in candidatos:
        texto = str(valor or "").strip()
        if not texto:
            continue
        ruta = Path(texto).expanduser()
        if not ruta.is_absolute():
            ruta = ROOT_DIR / ruta
        ruta = ruta.resolve()
        if ruta.is_dir() and ruta != ROOT_DIR and ruta.is_relative_to(ROOT_DIR):
            return ruta
        if ruta.is_file():
            for padre in ruta.parents:
                if padre == ROOT_DIR:
                    break
                if (padre / "renders").is_dir():
                    return padre
    return None


def video_final(renders: Path) -> Path | None:
    metadata_path = renders / "metadata.json"
    if metadata_path.is_file():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8", errors="replace"))
            nombre = str(metadata.get("video") or "").strip()
            if nombre:
                candidato = renders / nombre
                if candidato.is_file():
                    return candidato
        except (OSError, json.JSONDecodeError):
            pass
    mp4s = [ruta for ruta in renders.glob("*.mp4") if ruta.is_file()]
    return max(mp4s, key=lambda ruta: ruta.stat().st_mtime) if mp4s else None


def limpiar_proyecto(proyecto: Path, dry_run: bool = False) -> int:
    eliminados = 0
    renders = proyecto / "renders"
    if renders.is_dir():
        final = video_final(renders)
        conservar = set(ARCHIVOS_PROTEGIDOS)
        if final is not None:
            conservar.add(final.name)
        for ruta in renders.iterdir():
            if ruta.name in conservar:
                continue
            if dry_run:
                eliminados += 1
                continue
            try:
                if ruta.is_dir() and not ruta.is_symlink():
                    shutil.rmtree(ruta)
                else:
                    ruta.unlink()
                eliminados += 1
            except OSError:
                pass

    cache = proyecto / ".hyperframes"
    if cache.is_dir():
        if dry_run:
            eliminados += 1
        else:
            shutil.rmtree(cache, ignore_errors=True)
            eliminados += 1
    return eliminados


def limpiar(dias: int = DIAS, dry_run: bool = False) -> dict[str, Any]:
    if not QUEUE_PATH.is_file():
        return {"proyectos": 0, "eliminados": 0, "omitidos": []}

    try:
        datos = json.loads(QUEUE_PATH.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError) as error:
        log(f"No se pudo leer schedule_queue.json: {error}")
        return {"proyectos": 0, "eliminados": 0, "omitidos": []}

    limite = datetime.now(timezone.utc) - timedelta(days=dias)
    proyectos: dict[Path, str] = {}
    for tarea in datos.get("tareas", []):
        if not isinstance(tarea, dict):
            continue
        fecha = fecha_publicacion(tarea)
        if fecha is None or fecha > limite:
            continue
        proyecto = resolver_proyecto(tarea)
        if proyecto is None or not proyecto.is_relative_to(ROOT_DIR):
            continue
        if "_shared" in proyecto.parts:
            continue
        proyectos.setdefault(proyecto, fecha.isoformat())

    total = 0
    for proyecto, fecha in proyectos.items():
        borrados = limpiar_proyecto(proyecto, dry_run)
        total += borrados
        log(f"{'DRY-RUN ' if dry_run else ''}{proyecto.name}: publicado {fecha}, {borrados} temporales")

    return {
        "proyectos": len(proyectos),
        "eliminados": total,
        "omitidos": [str(proyecto) for proyecto in proyectos],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Limpia temporales de proyectos publicados hace más de 7 días.")
    parser.add_argument("--dry-run", action="store_true", help="Muestra qué se borraría sin eliminar")
    parser.add_argument("--dias", type=int, default=DIAS, help="Antigüedad mínima en días")
    args = parser.parse_args(argv)

    resultado = limpiar(max(1, args.dias), args.dry_run)
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
