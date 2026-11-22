from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

import texto_utf8

PUBLISHER_DIR = Path(__file__).resolve().parent
ROOT_DIR = PUBLISHER_DIR.parent.parent
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]
COMMENT_SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]
COMODINES = {"drones", "drone", "shorts", "short", "fyp", "auradrones", "viral", "tiktok", "youtube"}


def load_config() -> Path:
    load_dotenv(PUBLISHER_DIR / ".env", override=False)
    raw = os.getenv("YOUTUBE_CLIENT_SECRET_PATH", "").strip()
    if not raw:
        raise RuntimeError("YouTube: falta YOUTUBE_CLIENT_SECRET_PATH en .env")

    path = Path(raw).expanduser()
    if path.is_absolute():
        if not path.exists():
            raise RuntimeError(f"YouTube: no existe client_secret en {path}")
        return path

    for base in (PUBLISHER_DIR, Path.cwd(), ROOT_DIR):
        candidate = (base / path).resolve()
        if candidate.exists():
            return candidate

    raise RuntimeError(f"YouTube: no existe client_secret en {PUBLISHER_DIR / path}")


def load_credentials(client_secret: Path, token_path: Path, interactivo: bool = False) -> Any:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    credentials = None
    if token_path.exists():
        data = texto_utf8.leer_json_utf8(token_path)
        credentials = Credentials.from_authorized_user_info(data, SCOPES)

    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        texto_utf8.escribir_texto_utf8(token_path, credentials.to_json())

    if not credentials or not credentials.valid:
        if not interactivo:
            raise RuntimeError("YouTube: token inválido o expirado; requiere autorización interactiva")
        flow = InstalledAppFlow.from_client_secrets_file(str(client_secret), SCOPES)
        credentials = flow.run_local_server(port=0)
        texto_utf8.escribir_texto_utf8(token_path, credentials.to_json())

    return credentials


def clean_tags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = value.replace(",", " ").split()
    elif isinstance(value, (list, tuple, set)):
        items = [str(item) for item in value]
    else:
        items = [str(value)]

    tags: list[str] = []
    for item in items:
        tag = texto_utf8.limpiar_utf8(item).strip().lstrip("#").replace(" ", "")
        if tag and tag not in tags:
            tags.append(tag)
    return tags[:15]


def limpiar(texto: Any) -> str:
    return re.sub(r"\s+", " ", texto_utf8.limpiar_utf8(texto)).strip()


def ultima_pregunta(texto: Any) -> str:
    lineas = [limpiar(linea) for linea in str(texto or "").splitlines() if limpiar(linea)]
    for linea in reversed(lineas):
        if "?" in linea:
            return linea
    return ""


def pregunta_detonadora(config: dict[str, Any], caption: str) -> str:
    configurada = limpiar(
        config.get("pregunta_detonadora")
        or config.get("pregunta_cta")
        or config.get("cta")
        or config.get("pregunta")
    )
    if configurada:
        return texto_utf8.limpiar_utf8(configurada)[:500]
    de_descripcion = ultima_pregunta(config.get("description"))
    if de_descripcion:
        return texto_utf8.limpiar_utf8(de_descripcion)[:500]
    de_caption = ultima_pregunta(caption)
    if de_caption:
        return texto_utf8.limpiar_utf8(de_caption)[:500]

    titulo = limpiar(config.get("title") or config.get("titulo")) or limpiar(caption.splitlines()[0] if caption else "")
    tema = ""
    for hashtag in clean_tags(config.get("hashtags")):
        if hashtag.casefold() not in COMODINES and len(hashtag) >= 4:
            tema = hashtag
            break
    if not tema:
        tema = titulo[:60].strip(" .:-")
    if not tema:
        tema = "este consejo"
    plantillas = (
        f"¿Ya probaste {tema} en tu próximo vuelo? Cuéntanos qué resultado obtuviste.",
        f"¿Tú usas {tema} o lo harías de otra forma? Te leo en comentarios.",
        f"¿Te ha pasado con {tema}? Guarda el tip y comparte tu experiencia.",
    )
    return texto_utf8.limpiar_utf8(plantillas[len(titulo) % len(plantillas)])[:500]


def publicar_primer_comentario(credenciales: Any, video_id: str, pregunta: str) -> bool:
    if not video_id or not pregunta:
        return False
    try:
        if hasattr(credenciales, "has_scopes") and not credenciales.has_scopes(COMMENT_SCOPES):
            print("[AVISO] YouTube: token sin scope youtube.force-ssl; se omite el primer comentario", file=sys.stderr)
            return False
        from googleapiclient.discovery import build

        youtube = build("youtube", "v3", credentials=credenciales, cache_discovery=False)
        respuesta = youtube.commentThreads().insert(
            part="snippet",
            body={
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {"snippet": {"textOriginal": texto_utf8.limpiar_utf8(pregunta)}},
                }
            },
        ).execute()
        hilo = str(respuesta.get("id", ""))
        if hilo:
            try:
                youtube.commentThreads().setModerationStatus(
                    id=[hilo], moderationStatus="approved"
                ).execute()
            except Exception as aviso:
                print(
                    f"[AVISO] YouTube: comentario publicado pero no aprobado automáticamente: {type(aviso).__name__}: {aviso}",
                    file=sys.stderr,
                )
        return True
    except Exception as error:
        print(f"[AVISO] YouTube: primer comentario no publicado: {type(error).__name__}: {error}", file=sys.stderr)
        return False


def subir_miniatura(youtube: Any, video_id: str, video_path: Path) -> str:
    """Sube portada específica de YouTube como thumbnail personalizado si existe."""
    from googleapiclient.http import MediaFileUpload

    candidatos = [video_path.parent / "portada_youtube.jpg", video_path.parent / "cover.jpg", video_path.parent / "portada.jpg"]
    cover = next((c for c in candidatos if c.is_file()), None)
    if not video_id or cover is None:
        return ""
    try:
        youtube.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(str(cover), mimetype="image/jpeg")).execute()
        return str(cover)
    except Exception as error:
        print(f"[AVISO] YouTube: miniatura no subida: {type(error).__name__}: {error}", file=sys.stderr)
        return ""


def publicar(
    video_path: Path,
    config: dict[str, Any],
    caption: str,
    auto_schedule: bool = False,
    scheduled_at: str | None = None,
    interactivo: bool = False,
) -> dict[str, Any]:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    client_secret = load_config()
    credentials = load_credentials(client_secret, PUBLISHER_DIR / "youtube_token.json", interactivo=interactivo)
    youtube = build("youtube", "v3", credentials=credentials, cache_discovery=False)

    privacidad = str(config.get("privacidad", "public")).lower()
    if privacidad not in {"public", "private", "unlisted"}:
        privacidad = "public"

    status: dict[str, Any] = {
        "privacyStatus": privacidad,
        "selfDeclaredMadeForKids": False,
    }
    if auto_schedule and scheduled_at:
        status["privacyStatus"] = "private"
        status["publishAt"] = scheduled_at

    body: dict[str, Any] = {
        "snippet": {
            "title": texto_utf8.limpiar_utf8(config.get("title") or config.get("titulo") or video_path.stem)[:100],
            "description": texto_utf8.limpiar_utf8(caption)[:5000],
            "tags": clean_tags(config.get("hashtags")),
            "categoryId": "22",
        },
        "status": status,
    }

    media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True)
    response = youtube.videos().insert(part="snippet,status", body=body, media_body=media).execute()
    video_id = str(response.get("id", ""))
    comentario_publicado = False
    cover_subida = ""
    if video_id:
        cover_subida = subir_miniatura(youtube, video_id, video_path)
        comentario_publicado = publicar_primer_comentario(
            credentials, video_id, pregunta_detonadora(config, caption)
        )

    return {
        "plataforma": "youtube",
        "id": video_id,
        "url": f"https://www.youtube.com/watch?v={video_id}" if video_id else "",
        "estado": "programado" if auto_schedule and scheduled_at else "publicado",
        "scheduled_at": scheduled_at if auto_schedule and scheduled_at else "",
        "comentario_publicado": comentario_publicado,
        "cover": cover_subida,
    }
