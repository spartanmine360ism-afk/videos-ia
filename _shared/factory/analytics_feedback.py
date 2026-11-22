from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT_DIR = Path(__file__).resolve().parents[2]
FACTORY_DIR = Path(__file__).resolve().parent
PUBLISHER_DIR = ROOT_DIR / "_shared" / "publisher"
TOKEN_PATH = PUBLISHER_DIR / "youtube_token.json"
QUEUE_PATH = PUBLISHER_DIR / "schedule_queue.json"
REPORT_PATH = FACTORY_DIR / "analytics_feedback.json"
SCOPES = ["https://www.googleapis.com/auth/yt-analytics.readonly"]
DIAS_POR_DEFECTO = 90
STOPWORDS = {
    "con", "del", "las", "los", "una", "uno", "por", "para", "que", "como", "más", "mas", "este", "esta",
    "sus", "porque", "ante", "sin", "the", "and", "for", "with", "from", "that", "this", "how", "video",
    "videos", "drone", "drones", "fpv", "aura", "auradrones", "short", "shorts", "youtube", "nuevo", "new",
}


def limpiar(texto: Any) -> str:
    return re.sub(r"\s+", " ", str(texto or "")).strip()


def normalizar(texto: Any) -> str:
    valor = unicodedata.normalize("NFKD", str(texto or ""))
    valor = "".join(caracter for caracter in valor if not unicodedata.combining(caracter))
    return re.sub(r"\s+", " ", valor.casefold()).strip()


def tokens(texto: Any) -> set[str]:
    return {palabra for palabra in re.findall(r"[a-z0-9]{4,}", normalizar(texto)) if palabra not in STOPWORDS}


def fecha_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def cargar_token() -> dict[str, Any]:
    if not TOKEN_PATH.is_file():
        raise RuntimeError("Falta _shared/publisher/youtube_token.json")
    try:
        datos = json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"youtube_token.json inválido: {error}") from error
    if not isinstance(datos, dict):
        raise RuntimeError("youtube_token.json debe ser un objeto JSON")
    return datos


def credenciales() -> Any:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    datos = cargar_token()
    credencial = Credentials.from_authorized_user_info(datos, SCOPES)
    scopes = set(datos.get("scopes") or datos.get("scope") or [])
    if isinstance(datos.get("scope"), str):
        scopes.update(datos["scope"].split())
    if not set(SCOPES).issubset(scopes):
        raise RuntimeError("youtube_token.json sin scope yt-analytics.readonly")

    if credencial.expired and credencial.refresh_token:
        credencial.refresh(Request())
        temporal = TOKEN_PATH.with_name(TOKEN_PATH.name + ".tmp")
        temporal.write_text(credencial.to_json(), encoding="utf-8")
        temporal.replace(TOKEN_PATH)

    if not credencial.valid:
        raise RuntimeError("Token de YouTube vencido; requiere renovación interactiva")
    return credencial


def metadatos_desde_cola() -> dict[str, dict[str, Any]]:
    mapa: dict[str, dict[str, Any]] = {}
    if not QUEUE_PATH.is_file():
        return mapa
    try:
        datos = json.loads(QUEUE_PATH.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return mapa

    for tarea in datos.get("tareas", []):
        if not isinstance(tarea, dict):
            continue
        resultado = tarea.get("resultado") if isinstance(tarea.get("resultado"), dict) else {}
        video_id = limpiar(tarea.get("video_id") or resultado.get("id"))
        if not video_id:
            candidato = limpiar(tarea.get("id"))
            if candidato and not candidato.casefold().startswith("task"):
                video_id = candidato
        if not video_id:
            continue
        metadata = tarea.get("metadata") if isinstance(tarea.get("metadata"), dict) else {}
        config = tarea.get("config") if isinstance(tarea.get("config"), dict) else metadata.get("youtube", {})
        if not isinstance(config, dict):
            config = {}
        titulo = limpiar(config.get("title") or config.get("titulo") or metadata.get("title"))
        if not titulo:
            continue
        mapa[video_id] = {
            "titulo": titulo,
            "plataforma": limpiar(tarea.get("plataforma")),
            "gancho_id": str(config.get("gancho_id") or "").strip().upper(),
            "gancho_variante": limpiar(config.get("gancho_variante")),
            "serie_id": limpiar(config.get("serie_id")),
            "episodio": config.get("episodio") or "",
            "pregunta_detonadora": limpiar(config.get("pregunta_detonadora")),
        }
    return mapa


def consultar_analytics(dias: int) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    from googleapiclient.discovery import build

    credencial = credenciales()
    analytics = build("youtubeAnalytics", "v2", credentials=credencial, cache_discovery=False)
    fin = date.today()
    inicio = fin - timedelta(days=dias)
    comun = {
        "ids": "channel==MINE",
        "startDate": inicio.isoformat(),
        "endDate": fin.isoformat(),
        "metrics": "views,averageViewPercentage,averageViewDuration",
        "sort": "-views",
        "maxResults": 50,
    }

    respuesta: dict[str, Any] | None = None
    avisos: list[str] = []
    try:
        respuesta = analytics.reports().query(
            **comun,
            dimensions="video,creatorContentType",
            filters="creatorContentType==SHORTS",
        ).execute()
    except Exception as error:
        avisos.append(f"filtro SHORTS no disponible: {type(error).__name__}: {error}")
        try:
            respuesta = analytics.reports().query(**comun, dimensions="video").execute()
        except Exception as error2:
            raise RuntimeError(f"YouTube Analytics rechazó la consulta: {type(error2).__name__}: {error2}") from error2

    columnas = [limpiar(item.get("name")) for item in respuesta.get("columnHeaders", [])]
    filas = respuesta.get("rows", [])
    metadatos = metadatos_desde_cola()
    vistas_maximas = 0
    registros: list[dict[str, Any]] = []

    for fila in filas:
        valores = dict(zip(columnas, fila))
        vistas = int(float(valores.get("views") or 0))
        vistas_maximas = max(vistas_maximas, vistas)
        video_id = limpiar(valores.get("video") or valores.get("id"))
        contexto = metadatos.get(video_id, {})
        titulo = contexto.get("titulo") or limpiar(valores.get("title")) or f"Short {video_id}"
        registros.append(
            {
                "video_id": video_id,
                "titulo": titulo,
                "vistas": vistas,
                "retencion_pct": round(float(valores.get("averageViewPercentage") or 0), 2),
                "duracion_promedio_s": round(float(valores.get("averageViewDuration") or 0), 2),
                "gancho_id": contexto.get("gancho_id", ""),
                "gancho_variante": contexto.get("gancho_variante", ""),
                "serie_id": contexto.get("serie_id", ""),
                "episodio": contexto.get("episodio", ""),
                "plataforma": contexto.get("plataforma", "youtube"),
            }
        )

    ganadores: list[dict[str, Any]] = []
    for registro in registros:
        if registro["vistas"] <= 0:
            continue
        peso = 1.0
        if vistas_maximas:
            peso += 5 * registro["vistas"] / vistas_maximas
        peso += 4 * min(100.0, max(0.0, registro["retencion_pct"])) / 100
        ganadores.append(
            {
                **registro,
                "peso": round(min(10.0, peso), 2),
                "keywords": sorted(tokens(registro["titulo"]))[:14],
            }
        )

    ganadores.sort(key=lambda item: (item["peso"], item["vistas"]), reverse=True)
    ganadores = ganadores[:20]
    return ganadores, avisos, resumir_experimentos(ganadores)


def resumir_experimentos(ganadores: list[dict[str, Any]]) -> list[dict[str, Any]]:
    agrupados: dict[str, list[dict[str, Any]]] = {}
    for ganador in ganadores:
        variante = ganador.get("gancho_id") or "sin_id"
        agrupados.setdefault(variante, []).append(ganador)
    experimentos: list[dict[str, Any]] = []
    for variante, items in sorted(agrupados.items()):
        vistas = sum(int(float(item.get("vistas") or 0)) for item in items)
        retencion = sum(float(item.get("retencion_pct") or 0) for item in items) / len(items)
        experimentos.append(
            {
                "experimento": "gancho",
                "variante": variante,
                "publicaciones": len(items),
                "vistas": vistas,
                "retencion_promedio_pct": round(retencion, 2),
            }
        )
    experimentos.sort(key=lambda item: item["retencion_promedio_pct"], reverse=True)
    return experimentos


def cargar_ganadores() -> list[dict[str, Any]]:
    if not REPORT_PATH.is_file():
        return []
    try:
        datos = json.loads(REPORT_PATH.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return []
    ganadores = datos.get("ganadores", [])
    return ganadores if isinstance(ganadores, list) else []


def guardar(datos: dict[str, Any]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporal = REPORT_PATH.with_name(REPORT_PATH.name + ".tmp")
    temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporal.replace(REPORT_PATH)


def actualizar(dias: int = DIAS_POR_DEFECTO) -> dict[str, Any]:
    errores: list[str] = []
    experimentos: list[dict[str, Any]] = []
    try:
        ganadores, avisos, experimentos = consultar_analytics(dias)
        errores.extend(avisos)
    except Exception as error:
        ganadores = cargar_ganadores()
        errores.append(f"{type(error).__name__}: {error}")

    datos = {
        "actualizado_en": fecha_iso(),
        "dias_consultados": dias,
        "fuente": "YouTube Analytics API v2 · channel==MINE · Shorts",
        "total_ganadores": len(ganadores),
        "ganadores": ganadores,
        "experimentos": experimentos,
        "ganador_ab": experimentos[0] if experimentos else {},
        "errores": errores[:10],
    }
    guardar(datos)
    return datos


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bucle de aprendizaje con YouTube Analytics.")
    parser.add_argument("--dias", type=int, default=DIAS_POR_DEFECTO, help="Ventana de consulta en días")
    args = parser.parse_args(argv)

    datos = actualizar(max(1, args.dias))
    print(f"Reporte escrito: {REPORT_PATH}")
    print(f"Ganadores: {datos['total_ganadores']} | Avisos: {len(datos['errores'])}")
    for aviso in datos["errores"]:
        print(f"AVISO: {aviso}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
