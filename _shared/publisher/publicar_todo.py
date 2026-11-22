from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

import meta_upload
import metadata_viral
import scheduler_manager
import texto_utf8
import tiktok_upload
import youtube_upload

PUBLISHER_DIR = Path(__file__).resolve().parent
ROOT_DIR = PUBLISHER_DIR.parent.parent
PLATAFORMAS = ("youtube", "facebook", "instagram", "tiktok")
PLATAFORMAS_DIFERIDAS = {"tiktok", "instagram"}
PLATAFORMAS_NATIVAS = {"youtube", "facebook"}
LIMITES_HASHTAGS = metadata_viral.LIMITES_HASHTAGS


def resolve_project(value: str) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path

    for base in (Path.cwd(), ROOT_DIR):
        candidate = (base / path).resolve()
        if candidate.exists():
            return candidate

    return (ROOT_DIR / path).resolve()


def load_metadata(renders_dir: Path) -> dict[str, Any]:
    metadata_path = renders_dir / "metadata.json"
    if not metadata_path.exists():
        raise FileNotFoundError(f"No existe {metadata_path}")

    metadata = texto_utf8.leer_json_utf8(metadata_path)
    if not isinstance(metadata, dict):
        raise ValueError("metadata.json debe ser un objeto JSON")

    metadata, _ = metadata_viral.normalizar_metadata(metadata, ruta=metadata_path)
    validar_metadata(metadata)
    return metadata


def find_video(renders_dir: Path, metadata: dict[str, Any]) -> Path:
    for key in ("video", "archivo", "mp4"):
        value = metadata.get(key)
        if value:
            candidate = renders_dir / str(value)
            if candidate.is_file():
                return candidate
            print(f"[AVISO] metadata.json {key} apunta a un MP4 inexistente: {candidate}", file=sys.stderr)

    videos = [path for path in renders_dir.glob("*.mp4") if path.is_file()]
    if not videos:
        raise FileNotFoundError(f"No hay MP4 en {renders_dir}")

    return max(videos, key=lambda path: path.stat().st_mtime)


def hashtags(value: Any) -> list[str]:
    if isinstance(value, str):
        items = value.replace(",", " ").split()
    elif isinstance(value, (list, tuple, set)):
        items = [str(item) for item in value]
    elif value is None:
        items = []
    else:
        items = [str(value)]

    result: list[str] = []
    for item in items:
        tag = item.strip().lstrip("#").replace(" ", "")
        if tag and tag not in result:
            result.append(tag)
    return result


def platform_config(metadata: dict[str, Any], platform: str) -> dict[str, Any]:
    metadata = texto_utf8.limpiar_datos_utf8(metadata) if isinstance(metadata, dict) else {}
    block = metadata.get(platform)
    if not isinstance(block, dict):
        block = metadata

    def valor(*keys: str) -> Any:
        for key in keys:
            if block.get(key):
                return block[key]
            if metadata.get(key):
                return metadata[key]
        return None

    config: dict[str, Any] = {
        "title": str(valor("title", "titulo") or "").strip(),
        "description": str(valor("description", "descripcion") or "").strip(),
        "pregunta_detonadora": str(
            valor("pregunta_detonadora", "pregunta_cta", "cta", "pregunta") or ""
        ).strip(),
        "hashtags": hashtags(valor("hashtags")),
        "privacidad": str(valor("privacidad") or "public").strip().lower(),
    }

    experimento = metadata.get("experimento_ab") if isinstance(metadata.get("experimento_ab"), dict) else {}
    gancho_a = str(experimento.get("gancho_a") or "").strip()
    gancho_b = str(experimento.get("gancho_b") or "").strip()
    asignacion = experimento.get("asignacion") if isinstance(experimento.get("asignacion"), dict) else {}
    por_defecto = {"youtube": "A", "tiktok": "B"}.get(platform, "")
    gancho_id = str(block.get("gancho_id") or asignacion.get(platform) or por_defecto or "").upper()
    gancho_variante = gancho_b if gancho_id == "B" else gancho_a if gancho_id == "A" else ""

    if platform == "youtube" and gancho_variante and len(gancho_variante) < 55:
        config["title"] = gancho_variante
    elif platform == "tiktok" and gancho_variante:
        lineas = config["description"].splitlines()
        if lineas:
            lineas[0] = gancho_variante
            config["description"] = "\n".join(lineas)

    serie = metadata.get("serie") if isinstance(metadata.get("serie"), dict) else {}
    config.update(
        {
            "gancho_id": gancho_id,
            "gancho_variante": gancho_variante,
            "gancho_a": gancho_a,
            "gancho_b": gancho_b,
            "serie_id": str(serie.get("id") or metadata.get("serie_id") or "").strip(),
            "episodio": serie.get("episodio") or metadata.get("episodio") or "",
            "total_episodios": serie.get("total") or metadata.get("total_episodios") or "",
            "adelanto": str(serie.get("adelanto") or metadata.get("adelanto") or "").strip(),
        }
    )
    metadata_viral.normalizar_config(platform, config, metadata=metadata)
    return config


def primera_linea(texto: Any) -> str:
    for linea in str(texto or "").splitlines():
        limpia = linea.strip().lstrip("•-–—").strip()
        if limpia:
            return limpia
    return ""


def normalizar(texto: Any) -> str:
    return " ".join(str(texto or "").casefold().split())


def claves_copy(config: dict[str, Any]) -> tuple[str, str, tuple[str, ...]]:
    descripcion = str(config.get("description", ""))
    titulo = str(config.get("title", "")).strip()
    gancho = titulo or primera_linea(descripcion)
    return (
        normalizar(gancho),
        normalizar(primera_linea(descripcion)),
        tuple(sorted(tag.casefold() for tag in hashtags(config.get("hashtags")))),
    )


def copy_repetido(actual: tuple[str, str, tuple[str, ...]], anterior: tuple[str, str, tuple[str, ...]]) -> str | None:
    if actual[0] and actual[0] == anterior[0]:
        return "gancho"
    if actual[1] and actual[1] == anterior[1]:
        return "frase de apertura"
    if actual[2] and actual[2] == anterior[2]:
        return "combinación de hashtags"
    return None


def validar_config_plataforma(platform: str, config: dict[str, Any]) -> None:
    minimo, maximo = LIMITES_HASHTAGS.get(platform, (0, 0))
    descripcion = str(config.get("description", "")).strip()
    tags = hashtags(config.get("hashtags"))
    gancho_id = str(config.get("gancho_id") or "").strip().upper()
    if gancho_id and gancho_id not in {"A", "B"}:
        raise ValueError(f"metadata.json: {platform}.gancho_id debe ser A o B")

    if not descripcion:
        raise ValueError(f"metadata.json: {platform}.description está vacía")
    if not minimo <= len(tags) <= maximo:
        raise ValueError(f"metadata.json: {platform} debe tener entre {minimo} y {maximo} hashtags; tiene {len(tags)}")

    texto = descripcion.casefold()
    if platform == "youtube":
        title = str(config.get("title", "")).strip()
        if not title:
            raise ValueError("metadata.json: youtube.title es obligatorio")
        if len(title) >= 55:
            raise ValueError(f"metadata.json: youtube.title debe tener menos de 55 caracteres; tiene {len(title)}")
        if "shorts" not in [tag.casefold() for tag in tags]:
            raise ValueError("metadata.json: youtube.hashtags debe incluir Shorts")
    elif platform == "tiktok":
        if len(primera_linea(descripcion)) < 12:
            raise ValueError("metadata.json: tiktok.description necesita un gancho viral en la primera línea")
        if not any(palabra in texto for palabra in ("guarda", "comenta", "cuént", "opina")):
            raise ValueError("metadata.json: tiktok.description debe provocar guardados o comentarios")
    elif platform == "instagram":
        lineas = [linea.strip() for linea in descripcion.splitlines() if linea.strip()]
        if not any(linea.startswith(("•", "-", "–", "—")) for linea in lineas):
            raise ValueError("metadata.json: instagram.description necesita un resumen en viñetas")
        if not any(palabra in texto for palabra in ("guarda", "comparte")):
            raise ValueError("metadata.json: instagram.description necesita CTA para guardar o compartir")
    elif platform == "facebook":
        if not any(palabra in texto for palabra in ("comenta", "cuént", "comparte", "opina")):
            raise ValueError("metadata.json: facebook.description debe invitar a comentar, opinar o compartir")


def validar_metadata(metadata: dict[str, Any], verificar_cola: bool = True, ignorar_id: str | None = None) -> None:
    metadata, _ = metadata_viral.normalizar_metadata(metadata)
    for platform in PLATAFORMAS:
        bloque = metadata.get(platform)
        if not isinstance(bloque, dict):
            raise ValueError(f"metadata.json falta el bloque '{platform}'")
        validar_config_plataforma(platform, platform_config(metadata, platform))

    if not verificar_cola:
        return

    actuales = {platform: claves_copy(platform_config(metadata, platform)) for platform in PLATAFORMAS}
    for tarea in scheduler_manager.listar_tareas():
        if not isinstance(tarea, dict) or tarea.get("id") == ignorar_id:
            continue
        if str(tarea.get("estado", "")) in {"cancelled", "failed"}:
            continue

        plataforma_tarea = str(tarea.get("plataforma", "")).strip().lower()
        config_anterior = tarea.get("config")
        if isinstance(config_anterior, dict) and plataforma_tarea in actuales:
            motivo = copy_repetido(actuales[plataforma_tarea], claves_copy(config_anterior))
            if motivo:
                raise ValueError(
                    f"Copy repetido en {plataforma_tarea}: {motivo} ya usado en la tarea {tarea.get('id', '')}"
                )

        metadata_anterior = tarea.get("metadata")
        if not isinstance(metadata_anterior, dict):
            continue
        for platform in PLATAFORMAS:
            motivo = copy_repetido(actuales[platform], claves_copy(platform_config(metadata_anterior, platform)))
            if motivo:
                raise ValueError(
                    f"Copy repetido en {platform}: {motivo} ya usado en la tarea {tarea.get('id', '')}"
                )


def caption_for(config: dict[str, Any], max_length: int, include_title: bool = True) -> str:
    titulo = str(config.get("title", "")).strip() if include_title else ""
    descripcion = str(config.get("description", "")).strip()
    tags = " ".join(f"#{tag}" for tag in hashtags(config.get("hashtags")))
    texto = "\n\n".join(part for part in (titulo, descripcion, tags) if part)
    return texto_utf8.limpiar_utf8(texto)[:max_length]


def short_caption_for(config: dict[str, Any], max_length: int = 150) -> str:
    titulo = (str(config.get("title", "")).strip() or primera_linea(config.get("description", "")))[:max_length]
    espacio = max_length - len(titulo) - (1 if titulo else 0)
    partes: list[str] = []
    if espacio > 0:
        for tag in hashtags(config.get("hashtags")):
            candidato = " ".join(partes + [f"#{tag}"])
            if len(candidato) <= espacio:
                partes.append(f"#{tag}")
    return texto_utf8.limpiar_utf8(f"{titulo} {' '.join(partes)}").strip()


def caption(metadata: dict[str, Any], max_length: int) -> str:
    return caption_for(platform_config(metadata, "youtube"), max_length)


def credentials_configured(platform: str) -> tuple[bool, str]:
    load_dotenv(PUBLISHER_DIR / ".env", override=False)
    platform = platform.strip().lower()
    if platform == "youtube":
        try:
            youtube_upload.load_config()
        except Exception as error:
            return False, str(error)
        token_path = PUBLISHER_DIR / "youtube_token.json"
        if not token_path.exists():
            return False, "falta youtube_token.json; autoriza OAuth una vez"
        try:
            data = texto_utf8.leer_json_utf8(token_path)
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            creds = Credentials.from_authorized_user_info(data, youtube_upload.SCOPES)
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                texto_utf8.escribir_texto_utf8(token_path, creds.to_json())
            if not creds or not creds.valid:
                return False, "youtube_token.json inválido o expirado; requiere renovación"
            return True, "vigente"
        except Exception as error:
            return False, f"token YouTube no válido: {type(error).__name__}: {error}"
    if platform == "tiktok":
        if not tiktok_upload.credentials_configured():
            return False, "faltan TIKTOK_CLIENT_KEY/TIKTOK_CLIENT_SECRET"
        if not tiktok_upload.access_token_configurado():
            return False, "TIKTOK_ACCESS_TOKEN requiere renovación"
        return True, "configurado"
    if platform == "facebook":
        token, page_id, _ = meta_upload.load_config()
        ok = bool(token and page_id)
        return ok, "" if ok else "faltan META_ACCESS_TOKEN/META_PAGE_ID"
    if platform == "instagram":
        token, _, instagram_id = meta_upload.load_config()
        ok = bool(token and instagram_id and meta_upload.video_url_available())
        return ok, "" if ok else "faltan credenciales/URL pública Instagram"
    return False, f"plataforma desconocida: {platform}"


def available_platforms() -> dict[str, bool]:
    resultado: dict[str, bool] = {}
    for plataforma in PLATAFORMAS:
        try:
            resultado[plataforma] = credentials_configured(plataforma)[0]
        except Exception as error:
            print(f"[AVISO] No se pudo verificar {plataforma}: {type(error).__name__}: {error}", file=sys.stderr)
            resultado[plataforma] = False
    return resultado


def _enqueue_deferred(platform: str, video_path: Path, metadata: dict[str, Any], slot: dict[str, Any]) -> dict[str, Any]:
    tarea = {
        "plataforma": platform,
        "video": str(video_path),
        "metadata": metadata,
        "config": platform_config(metadata, platform),
        "scheduled_at": slot["scheduled_at"],
        "scheduled_at_local": slot["scheduled_at_local"],
        "slot": slot["slot"],
        "estado": "pending",
        "tipo": "diferida",
    }
    creada = scheduler_manager.encolar_tarea(tarea)
    return {
        "plataforma": platform,
        "id": creada["id"],
        "url": "",
        "estado": "pending",
        "scheduled_at": slot["scheduled_at"],
    }


def _register_native(
    platform: str,
    video_path: Path,
    metadata: dict[str, Any],
    slot: dict[str, Any],
    resultado: dict[str, Any],
) -> None:
    scheduler_manager.encolar_tarea(
        {
            "plataforma": platform,
            "video": str(video_path),
            "metadata": metadata,
            "config": platform_config(metadata, platform),
            "scheduled_at": slot["scheduled_at"],
            "scheduled_at_local": slot["scheduled_at_local"],
            "slot": slot["slot"],
            "estado": "scheduled_native",
            "tipo": "nativa",
            "resultado": resultado,
        }
    )


def _enqueue_pendiente_credenciales(
    platform: str,
    video_path: Path,
    metadata: dict[str, Any],
    slot: dict[str, Any],
) -> dict[str, Any]:
    tipo = "diferida" if platform in PLATAFORMAS_DIFERIDAS else "nativa_pendiente"
    tarea = {
        "plataforma": platform,
        "video": str(video_path),
        "metadata": metadata,
        "config": platform_config(metadata, platform),
        "scheduled_at": slot["scheduled_at"],
        "scheduled_at_local": slot["scheduled_at_local"],
        "slot": slot["slot"],
        "estado": "pending_credentials",
        "tipo": tipo,
        "requiere_credenciales": True,
    }
    creada = scheduler_manager.encolar_tarea(tarea)
    return {
        "plataforma": platform,
        "id": creada["id"],
        "url": "",
        "estado": "pending_credentials",
        "scheduled_at": slot["scheduled_at"],
    }


def publish(
    platform: str,
    video_path: Path,
    metadata: dict[str, Any],
    slot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if slot is not None:
        if platform in PLATAFORMAS_DIFERIDAS:
            return _enqueue_deferred(platform, video_path, metadata, slot)
        if platform not in PLATAFORMAS_NATIVAS:
            raise ValueError(f"{platform} no admite programación")

    config = platform_config(metadata, platform)
    programado = slot is not None
    scheduled_at = str(slot["scheduled_at"]) if slot else None

    if platform == "youtube":
        resultado = youtube_upload.publicar(
            video_path, config, caption_for(config, 5000), programado, scheduled_at, interactivo=False
        )
    elif platform == "facebook":
        resultado = meta_upload.publicar_facebook(video_path, config, caption_for(config, 2200), programado, scheduled_at)
    elif platform == "instagram":
        resultado = meta_upload.publicar_instagram(video_path, config, caption_for(config, 2200), programado, scheduled_at)
    else:
        resultado = tiktok_upload.publicar(video_path, config, short_caption_for(config), programado, scheduled_at)

    if slot is not None:
        try:
            _register_native(platform, video_path, metadata, slot, resultado)
            resultado["cola_registrada"] = True
        except Exception as error:
            resultado["cola_registrada"] = False
            print(
                f"[AVISO] {platform}: publicado pero no se pudo registrar en la cola: {type(error).__name__}: {error}",
                file=sys.stderr,
            )
    return resultado


def parse_platforms(raw: str) -> list[str]:
    platforms: list[str] = []
    for item in raw.split(","):
        platform = item.strip().lower()
        if platform and platform not in platforms:
            platforms.append(platform)

    invalid = [platform for platform in platforms if platform not in PLATAFORMAS]
    if invalid:
        raise ValueError(f"Plataformas desconocidas: {', '.join(invalid)}")
    return platforms


PLATAFORMAS_AUTO_DEFAULT = ("youtube", "tiktok")
PLATAFORMAS_SIN_CREDENCIALES_SKIP = {"instagram", "facebook"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publica o programa el MP4 renderizado de un proyecto.")
    parser.add_argument("proyecto", help="Carpeta del proyecto, por ejemplo dji-sensores-tip")
    parser.add_argument(
        "--plataformas",
        default=None,
        help="Lista separada por comas: youtube,facebook,instagram,tiktok. Con --auto-schedule sin este flag: youtube,tiktok",
    )
    parser.add_argument(
        "--auto-schedule",
        action="store_true",
        help="Programa en horarios pico: nativo en YouTube y cola diferida en TikTok (Instagram/Facebook desactivados por defecto)",
    )
    args = parser.parse_args(argv)

    try:
        raw_plataformas = args.plataformas
        if raw_plataformas is None:
            raw_plataformas = ",".join(PLATAFORMAS_AUTO_DEFAULT if args.auto_schedule else PLATAFORMAS)
        platforms = parse_platforms(raw_plataformas)
        project_dir = resolve_project(args.proyecto)
        if not project_dir.is_dir():
            raise FileNotFoundError(f"No existe la carpeta de proyecto {project_dir}")

        renders_dir = project_dir / "renders"
        metadata = load_metadata(renders_dir)
        video_path = find_video(renders_dir, metadata)
        enabled = available_platforms()

        slots: dict[str, dict[str, Any]] = {}
        if args.auto_schedule:
            for platform in platforms:
                slots[platform] = scheduler_manager.asignar_siguiente_slot(platform)

        print(f"Video: {video_path}")
        resultados: list[dict[str, Any]] = []
        fallos: list[str] = []

        plataformas_explicitas = args.plataformas is not None
        for platform in platforms:
            if not enabled.get(platform):
                if not args.auto_schedule:
                    print(f"[SKIP] {platform}: credenciales o herramienta no configuradas")
                    continue
                if platform in PLATAFORMAS_SIN_CREDENCIALES_SKIP and not plataformas_explicitas:
                    print(f"[SKIP] {platform}: credenciales no configuradas (desactivado en auto-schedule)")
                    continue
                try:
                    resultado = _enqueue_pendiente_credenciales(
                        platform, video_path, metadata, slots[platform]
                    )
                    resultados.append(resultado)
                    print(
                        f"[QUEUE-CRED] {platform}: id={resultado['id']} estado=pending_credentials "
                        f"programado={resultado['scheduled_at']}"
                    )
                except Exception as error:
                    fallos.append(platform)
                    print(f"[ERROR] {platform}: {error}", file=sys.stderr)
                continue
            try:
                resultado = publish(platform, video_path, metadata, slots.get(platform))
                resultados.append(resultado)
                estado = resultado.get("estado", "")
                etiqueta = "QUEUE" if estado == "pending" else "OK"
                programacion = f" programado={resultado['scheduled_at']}" if resultado.get("scheduled_at") else ""
                print(
                    f"[{etiqueta}] {resultado['plataforma']}: "
                    f"id={resultado['id']} estado={estado}{programacion}"
                )
            except Exception as error:
                fallos.append(platform)
                print(f"[ERROR] {platform}: {error}", file=sys.stderr)

        if not resultados:
            return 1
        return 1 if len(fallos) == len(platforms) else 0

    except Exception as error:
        print(f"[FATAL] {type(error).__name__}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
