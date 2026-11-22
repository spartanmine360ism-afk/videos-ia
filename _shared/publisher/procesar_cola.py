from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import publicar_todo
import scheduler_manager as scheduler
import texto_utf8

PUBLISHER_DIR = Path(__file__).resolve().parent
ROOT_DIR = PUBLISHER_DIR.parent.parent
FACTORY_DIR = ROOT_DIR / "_shared" / "factory"
if str(FACTORY_DIR) not in sys.path:
    sys.path.insert(0, str(FACTORY_DIR))

import notificador_telegram

MODULOS = {
    "youtube": publicar_todo.youtube_upload,
    "facebook": publicar_todo.meta_upload,
    "instagram": publicar_todo.meta_upload,
    "tiktok": publicar_todo.tiktok_upload,
}
FUNCIONES = {
    "youtube": "publicar",
    "facebook": "publicar_facebook",
    "instagram": "publicar_instagram",
    "tiktok": "publicar",
}


def resolver_video(valor: Any, tarea: dict[str, Any] | None = None) -> Path:
    texto = str(valor or "").strip()
    if not texto:
        raise FileNotFoundError("la tarea no tiene ruta de video")

    path = Path(texto).expanduser()
    if path.is_absolute() and path.is_file():
        return path

    nombres = [path.name]
    if isinstance(tarea, dict):
        for fuente in (tarea.get("config"), tarea.get("metadata")):
            if not isinstance(fuente, dict):
                continue
            for clave in ("video", "archivo", "mp4", "nombre_video"):
                valor_fuente = fuente.get(clave)
                if valor_fuente:
                    nombre = Path(str(valor_fuente)).name
                    if nombre not in nombres:
                        nombres.append(nombre)
        proyectos = [
            str(tarea.get(clave))
            for clave in ("proyecto", "proyecto_nombre", "proyecto_dir")
            if tarea.get(clave)
        ]
    else:
        proyectos = []

    bases = [PUBLISHER_DIR, ROOT_DIR, Path.cwd()]
    bases.extend(ROOT_DIR / proyecto / "renders" for proyecto in proyectos)
    bases.extend(ROOT_DIR / proyecto for proyecto in proyectos)
    for base in bases:
        for nombre in nombres:
            candidato = (base / nombre).resolve()
            if candidato.is_file():
                return candidato
            en_renders = (base / "renders" / nombre).resolve()
            if en_renders.is_file():
                return en_renders

    raise FileNotFoundError(f"No existe el MP4 {texto}")


MAX_REINTENTOS = 2
JITTER_MIN = -8
JITTER_MAX = 12


def aplicar_jitter(tarea: dict[str, Any]) -> None:
    """Jitter aleatorio -8..+12 min, una sola vez por tarea."""
    if tarea.get("jitter_aplicado") or str(tarea.get("plataforma", "")).strip().lower() != "tiktok":
        return
    base = scheduler.parse_scheduled_at(tarea.get("scheduled_at"))
    if base is None:
        return
    delta = random.randint(JITTER_MIN, JITTER_MAX)
    nueva = base + timedelta(minutes=delta)
    tarea["scheduled_at_original"] = tarea.get("scheduled_at")
    tarea["scheduled_at"] = scheduler.iso_utc(nueva)
    tarea["scheduled_at_local"] = nueva.astimezone(scheduler.ZONA).isoformat()
    tarea["jitter_minutos"] = delta
    tarea["jitter_aplicado"] = True


def ejecutar(tarea: dict[str, Any]) -> dict[str, Any]:
    plataforma = str(tarea.get("plataforma", "")).strip().lower()
    if plataforma not in MODULOS:
        raise ValueError(f"plataforma desconocida en la cola: {plataforma}")

    video_path = resolver_video(tarea.get("video"), tarea)
    if video_path.stat().st_size <= 0:
        raise ValueError(f"MP4 vacío: {video_path}")
    metadata = tarea.get("metadata") if isinstance(tarea.get("metadata"), dict) else {}
    config = tarea.get("config")
    if not isinstance(config, dict):
        config = publicar_todo.platform_config(metadata, plataforma)
    else:
        config, _ = publicar_todo.metadata_viral.normalizar_config(
            plataforma, config, metadata=metadata
        )
    publicar_todo.validar_config_plataforma(plataforma, config)
    modulo = MODULOS[plataforma]
    funcion = getattr(modulo, FUNCIONES[plataforma])

    if plataforma == "youtube":
        caption = publicar_todo.caption_for(config, 5000)
    elif plataforma == "tiktok":
        caption = publicar_todo.short_caption_for(config)
    else:
        caption = publicar_todo.caption_for(config, 2200)

    opciones = {"interactivo": False} if plataforma == "youtube" else {}
    resultado = funcion(video_path, config, caption, **opciones)
    return resultado if isinstance(resultado, dict) else {"plataforma": plataforma, "id": "", "url": ""}


def marcar_error_tarea(tarea: dict[str, Any], mensaje: str, ahora: datetime, estado: str = "failed") -> bool:
    plataforma = tarea.get("plataforma", "?")
    tarea["estado"] = estado
    tarea["error"] = mensaje
    tarea["ultimo_intento"] = scheduler.iso_utc(ahora)
    tarea.pop("upload_inicio", None)
    print(f"[AVISO] {plataforma}: {mensaje}", file=sys.stderr)
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Procesa la cola de publicaciones programadas.")
    parser.add_argument("--dry-run", action="store_true", help="Muestra qué tareas están listas sin publicar")
    args = parser.parse_args(argv)

    cola = scheduler.cargar_cola()
    tareas = cola.get("tareas", [])
    ahora = datetime.now(timezone.utc)
    limite = ahora + timedelta(minutes=5)
    listas: list[tuple[datetime, dict[str, Any]]] = []
    habilitadas = publicar_todo.available_platforms()
    cambios = False

    for tarea in tareas:
        if not isinstance(tarea, dict):
            continue
        estado = str(tarea.get("estado", ""))
        plataforma = str(tarea.get("plataforma", "")).strip().lower()
        if estado in {"pending", "pending_credentials", "failed_retry", "uploading"}:
            if estado == "uploading":
                inicio = scheduler.parse_scheduled_at(tarea.get("upload_inicio"))
                if inicio is not None:
                    if inicio.tzinfo is None:
                        inicio = inicio.replace(tzinfo=timezone.utc)
                    if ahora - inicio < timedelta(minutes=30):
                        continue
                cambios = marcar_error_tarea(tarea, "carga interrumpida sin confirmación", ahora, "failed_retry")
                continue
            try:
                ruta_video = resolver_video(tarea.get("video"), tarea)
                if ruta_video.stat().st_size <= 0:
                    raise ValueError(f"MP4 vacío: {ruta_video}")
            except (FileNotFoundError, OSError, ValueError) as error:
                cambios = marcar_error_tarea(tarea, str(error), ahora)
                continue
        if estado == "pending_credentials":
            if not habilitadas.get(plataforma):
                if plataforma == "tiktok" and not tarea.get("aviso_renovacion_enviado"):
                    try:
                        notificador_telegram.notificar_tiktok_token_renovacion(tarea.get("video"), "TIKTOK_ACCESS_TOKEN requiere renovación o credenciales no configuradas")
                        tarea["aviso_renovacion_enviado"] = True
                        cambios = True
                    except Exception:
                        pass
                continue
            tarea["estado"] = "pending"
            tarea["promovida_en"] = scheduler.iso_utc(ahora)
            tarea["tipo"] = "diferida" if plataforma in publicar_todo.PLATAFORMAS_DIFERIDAS else "nativa"
            tarea.pop("requiere_credenciales", None)
            cambios = True
        elif estado == "failed_retry":
            if int(tarea.get("intentos", 0)) < MAX_REINTENTOS:
                tarea["estado"] = "pending"
                cambios = True
            else:
                continue
        elif estado != "pending":
            continue
        if plataforma == "tiktok":
            antes = tarea.get("scheduled_at")
            aplicar_jitter(tarea)
            if tarea.get("scheduled_at") != antes:
                cambios = True
        fecha = scheduler.parse_scheduled_at(tarea.get("scheduled_at"))
        if fecha is not None and fecha <= limite:
            listas.append((fecha, tarea))

    if cambios and not args.dry_run:
        scheduler.guardar_cola(cola)

    listas.sort(key=lambda item: item[0])
    if not listas:
        print("Cola sin tareas pendientes dentro de los próximos 5 minutos.")
        return 0

    for fecha, tarea in listas:
        plataforma = tarea.get("plataforma", "?")
        if args.dry_run:
            print(f"[DRY-RUN] {plataforma}: {fecha.isoformat()} id={tarea.get('id', '')}")
            continue
        tarea["estado"] = "uploading"
        tarea["upload_inicio"] = scheduler.iso_utc(datetime.now(timezone.utc))
        scheduler.guardar_cola(cola)
        try:
            resultado = ejecutar(tarea)
            tarea["estado"] = "published"
            tarea["publicado_en"] = scheduler.iso_utc(datetime.now(timezone.utc))
            tarea["resultado"] = resultado
            tarea.pop("error", None)
            print(f"[OK] {plataforma}: id={resultado.get('id', '')} enviado={tarea['publicado_en']}")
            config_tarea = tarea.get("config") if isinstance(tarea.get("config"), dict) else {}
            titulo = texto_utf8.limpiar_utf8(config_tarea.get("title") or config_tarea.get("titulo") or "")
            enlace = texto_utf8.limpiar_utf8(resultado.get("url", ""))
            try:
                notificador_telegram.notificar_publicacion_cola(plataforma, tarea.get("video"), titulo, enlace)
            except Exception:
                pass
        except Exception as error:
            tarea["intentos"] = int(tarea.get("intentos", 0)) + 1
            tarea["error"] = str(error)
            tarea["ultimo_intento"] = scheduler.iso_utc(datetime.now(timezone.utc))
            tarea["estado"] = "failed_retry" if tarea["intentos"] < MAX_REINTENTOS else "failed"
            print(f"[ERROR] {plataforma}: {error}", file=sys.stderr)
            detalle = str(error)
            if plataforma == "tiktok" and ("TIKTOK_ACCESS_TOKEN" in detalle or "401" in detalle or "access_token" in detalle.casefold()):
                try:
                    notificador_telegram.notificar_tiktok_token_renovacion(tarea.get("video"), detalle)
                except Exception:
                    pass
            elif plataforma == "youtube" and ("401" in detalle or "invalid_grant" in detalle.casefold() or "token" in detalle.casefold()):
                try:
                    notificador_telegram.notificar_alerta_token("youtube", detalle)
                except Exception:
                    pass

        scheduler.guardar_cola(cola)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
