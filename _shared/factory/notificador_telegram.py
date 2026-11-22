from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT_DIR = Path(__file__).resolve().parents[2]
PUBLISHER_DIR = ROOT_DIR / "_shared" / "publisher"
FACTORY_DIR = Path(__file__).resolve().parent
ENV_PATH = PUBLISHER_DIR / ".env"
QUEUE_PATH = PUBLISHER_DIR / "schedule_queue.json"
if str(PUBLISHER_DIR) not in sys.path:
    sys.path.insert(0, str(PUBLISHER_DIR))
if str(FACTORY_DIR) not in sys.path:
    sys.path.insert(0, str(FACTORY_DIR))

import texto_utf8
IDEAS_PATH = FACTORY_DIR / "ideas_pendientes.json"
OPORTUNIDADES_PATH = FACTORY_DIR / "oportunidades_colab.json"
ANALYTICS_PATH = FACTORY_DIR / "analytics_feedback.json"
ZONA = ZoneInfo("America/Mexico_City")
CUPO_DIARIO = 3
NOMBRES_PLATAFORMA = {
    "youtube": "YouTube Shorts",
    "tiktok": "TikTok",
}
ORDEN_PLATAFORMA = {"youtube": 0, "tiktok": 1}
PLATAFORMAS_REPORTE = {"youtube", "tiktok"}
LIMITE_TELEGRAM = 4000
_CREDENCIALES: tuple[str, str] | None = None


def cargar_credenciales() -> tuple[str, str]:
    load_dotenv(ENV_PATH, override=False)
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise RuntimeError(
            "Faltan TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID en "
            "_shared/publisher/.env"
        )
    return token, chat_id


def enviar_mensaje(texto: str, timeout: int = 20) -> dict[str, Any]:
    token, chat_id = cargar_credenciales()
    contenido = texto[:LIMITE_TELEGRAM]
    respuesta = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        headers={"Content-Type": "application/json; charset=utf-8"},
        json={
            "chat_id": chat_id,
            "text": contenido,
            "disable_web_page_preview": True,
        },
        timeout=timeout,
    )
    try:
        datos = respuesta.json()
    except ValueError:
        datos = {}
    if respuesta.status_code != 200 or not datos.get("ok"):
        detalle = str(datos.get("description") or respuesta.reason or "respuesta inválida")
        raise RuntimeError(f"Telegram rechazó el mensaje: HTTP {respuesta.status_code}: {detalle}")
    return datos


def _texto(valor: Any) -> str:
    return " ".join(texto_utf8.limpiar_utf8(valor).split())


def _credenciales_silenciosas() -> tuple[str, str] | None:
    global _CREDENCIALES
    if _CREDENCIALES is not None:
        return _CREDENCIALES
    try:
        _CREDENCIALES = cargar_credenciales()
    except Exception:
        return None
    return _CREDENCIALES


def _enviar_silencioso(texto: str) -> bool:
    try:
        if _credenciales_silenciosas() is None:
            return False
        datos = enviar_mensaje(texto, timeout=5)
        return bool(datos.get("ok"))
    except Exception:
        return False


def notificar_inicio_lote(faltantes: Any, fechas: Any = None) -> bool:
    if isinstance(faltantes, dict):
        total = sum(int(valor or 0) for valor in faltantes.values())
        fechas = list(faltantes.keys()) if fechas is None else fechas
    else:
        try:
            total = int(faltantes)
        except (TypeError, ValueError):
            total = 0
    if isinstance(fechas, dict):
        fechas = list(fechas.keys())
    elif isinstance(fechas, str):
        fechas = [fechas]
    fecha_texto = ", ".join(_texto(fecha) for fecha in (fechas or []) if _texto(fecha)) or "sin fecha definida"
    mensaje = (
        "AuraDrones | Inicio de lote\n"
        f"Videos faltantes: {total}\n"
        f"Fechas: {fecha_texto}"
    )
    return _enviar_silencioso(mensaje)


def notificar_etapa_idea(indice: Any, total: Any, tema: Any, paleta: Any = "", voz: Any = "") -> bool:
    lineas = [
        f"[1/5] Idea y estilo: video {_texto(indice)}/{_texto(total)}",
        f"Tema: {_texto(tema)}",
        f"Paleta: {_texto(paleta) or 'pendiente'}",
        f"Voz: {_texto(voz) or 'pendiente'}",
    ]
    return _enviar_silencioso("\n".join(lineas))


def notificar_etapa_guion_voz(indice: Any, total: Any, tema: Any, duracion_audio_s: Any, gancho: Any) -> bool:
    lineas = [
        f"[2/5] Guion y voz: video {_texto(indice)}/{_texto(total)}",
        f"Tema: {_texto(tema)}",
        f"Duración audio: {_texto(duracion_audio_s)} s",
        f"Gancho: {_texto(gancho)[:140]}",
    ]
    return _enviar_silencioso("\n".join(lineas))


def notificar_etapa_render_qa(indice: Any, total: Any, tema: Any, peso_mb: Any, textos_encimados: Any = 0, detalle: Any = "") -> bool:
    lineas = [
        f"[3/5] Render y QA visual: video {_texto(indice)}/{_texto(total)}",
        f"Tema: {_texto(tema)}",
        f"Peso MP4: {_texto(peso_mb)} MB",
        f"Inspección 3 frames clave: {_texto(textos_encimados)} textos encimados",
    ]
    if _texto(detalle):
        lineas.append(f"Detalle: {_texto(detalle)[:180]}")
    return _enviar_silencioso("\n".join(lineas))


def notificar_etapa_programado(indice: Any, total: Any, tema: Any, youtube_hora: Any = "", youtube_url: Any = "", tiktok_hora: Any = "") -> bool:
    lineas = [
        f"[4/5] Programado: video {_texto(indice)}/{_texto(total)}",
        f"Tema: {_texto(tema)}",
        f"YouTube Shorts: { _texto(youtube_hora) or 'sin hora asignada'}" + (f" | { _texto(youtube_url)}" if _texto(youtube_url) else ""),
        f"TikTok: turno en cola { _texto(tiktok_hora) or 'pendiente'}",
    ]
    return _enviar_silencioso("\n".join(lineas))


def notificar_etapa_publicado_vivo(plataforma: Any, titulo: Any = "", url: Any = "") -> bool:
    clave = str(plataforma).casefold()
    if clave not in PLATAFORMAS_REPORTE:
        return False
    nombre = NOMBRES_PLATAFORMA.get(clave, clave)
    lineas = [f"[5/5] Publicado en vivo en {nombre}"]
    if _texto(titulo):
        lineas.append(f"Título: {_texto(titulo)}")
    if _texto(url):
        lineas.append(f"URL: {_texto(url)}")
    return _enviar_silencioso("\n".join(lineas))


def notificar_alerta_reintento(tema: Any, etapa: Any, intento: Any, detalle: Any = "") -> bool:
    lineas = [
        f"⚠️ Alerta: reintento automático en {_texto(etapa)}",
        f"Tema: {_texto(tema)}",
        f"Intento: {_texto(intento)}",
    ]
    if _texto(detalle):
        lineas.append(f"Detalle: {_texto(detalle)[:220]}")
    return _enviar_silencioso("\n".join(lineas))


def notificar_alerta_token(plataforma: Any, detalle: Any = "") -> bool:
    clave = str(plataforma).casefold()
    nombre = NOMBRES_PLATAFORMA.get(clave, _texto(plataforma) or "plataforma")
    lineas = [f"⚠️ Alerta: token de {nombre} requiere renovación o no es válido"]
    if _texto(detalle):
        lineas.append(f"Detalle: {_texto(detalle)[:220]}")
    return _enviar_silencioso("\n".join(lineas))


def notificar_error_video(
    tema: Any,
    motivo: Any,
    fase: Any = "producción",
    reintento: Any = None,
    continuara: bool = True,
) -> bool:
    lineas = [
        "AuraDrones | Alerta de video",
        f"Tema: {_texto(tema)}",
        f"Fase: {_texto(fase)}",
        f"Motivo: {_texto(motivo)[:500]}",
    ]
    if reintento is not None:
        lineas.append(f"Reintento: {_texto(reintento)}")
    lineas.append(
        "Se continúa con el siguiente tema disponible." if continuara else "No hay más temas disponibles en este lote."
    )
    return _enviar_silencioso("\n".join(lineas))


def notificar_publicacion_cola(plataforma: Any, video: Any, titulo: Any = "", url: Any = "") -> bool:
    destino = _texto(titulo) or _texto(Path(str(video)).stem if video else "video")
    return notificar_etapa_publicado_vivo(plataforma, destino, url)


def notificar_inicio_cola(cantidad_tareas: int, modo: str = "cola") -> bool:
    mensaje = (
        "AuraDrones | Procesando cola\n"
        f"Modo: {_texto(modo)}\n"
        f"Tareas listas en ventana: {int(cantidad_tareas)}"
    )
    return _enviar_silencioso(mensaje)


def notificar_subiendo_video(plataforma: Any, video: Any, titulo: Any = "", programado_en: Any = "") -> bool:
    clave = str(plataforma or "").casefold()
    nombre = NOMBRES_PLATAFORMA.get(clave, _texto(plataforma) or "plataforma")
    destino = _texto(titulo) or _texto(Path(str(video)).stem if video else "video")
    lineas = [
        f"Subiendo video a {nombre}",
        f"Video: {destino}",
    ]
    if _texto(programado_en):
        lineas.append(f"Horario: {_texto(programado_en)}")
    return _enviar_silencioso("\n".join(lineas))



def notificar_tiktok_token_renovacion(video: Any = "", detalle: Any = "") -> bool:
    extra = _texto(detalle)
    if video:
        extra = f"{Path(str(video)).name}: {extra}" if extra else Path(str(video)).name
    return notificar_alerta_token("tiktok", extra or "TIKTOK_ACCESS_TOKEN requiere renovación")


def cargar_json(ruta: Path, defecto: dict[str, Any]) -> dict[str, Any]:
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8", errors="replace"))
        return datos if isinstance(datos, dict) else defecto
    except (OSError, json.JSONDecodeError):
        return defecto


def fecha_de(valor: Any) -> date | None:
    texto = str(valor or "").strip().replace("Z", "+00:00")
    if not texto:
        return None
    try:
        momento = datetime.fromisoformat(texto)
    except ValueError:
        return None
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=ZONA)
    return momento.astimezone(ZONA).date()


def fecha_objetivo(valor: date | str | None = None) -> date:
    if isinstance(valor, datetime):
        return valor.astimezone(ZONA).date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str) and valor.strip():
        return date.fromisoformat(valor.strip())
    return (datetime.now(ZONA) + timedelta(days=1)).date()


def normalizar(texto: Any) -> str:
    return " ".join(str(texto or "").casefold().split())


def nombre_proyecto_tarea(tarea: dict[str, Any]) -> str:
    proyecto = str(tarea.get("proyecto") or "").strip()
    if proyecto:
        return Path(proyecto).name
    video = str(tarea.get("video") or "").strip()
    if not video:
        return ""
    ruta = Path(video)
    if ruta.parent.name.casefold() == "renders":
        return ruta.parent.parent.name
    return ruta.stem


def tareas_por_proyecto(fecha: date) -> dict[str, list[dict[str, Any]]]:
    cola = cargar_json(QUEUE_PATH, {"tareas": []})
    resultado: dict[str, list[dict[str, Any]]] = {}
    for tarea in cola.get("tareas", []):
        if not isinstance(tarea, dict):
            continue
        estado = str(tarea.get("estado", "")).casefold()
        if estado in {"cancelled", "failed"}:
            continue
        fecha_tarea = fecha_de(tarea.get("scheduled_at_local")) or fecha_de(tarea.get("scheduled_at"))
        if fecha_tarea != fecha:
            continue
        proyecto = nombre_proyecto_tarea(tarea)
        if not proyecto:
            continue
        resultado.setdefault(proyecto, []).append(tarea)
    return resultado


def titulo_de_tarea(tarea: dict[str, Any], proyecto: str) -> str:
    config = tarea.get("config") if isinstance(tarea.get("config"), dict) else {}
    titulo = str(config.get("title") or config.get("titulo") or "").strip()
    return titulo or proyecto


def horarios_de(tareas: list[dict[str, Any]]) -> str:
    fragmentos: list[str] = []
    for tarea in sorted(
        tareas,
        key=lambda item: (
            ORDEN_PLATAFORMA.get(str(item.get("plataforma", "")).casefold(), 99),
            str(item.get("slot", "")),
        ),
    ):
        plataforma = str(tarea.get("plataforma", "")).casefold()
        if plataforma not in PLATAFORMAS_REPORTE:
            continue
        nombre = NOMBRES_PLATAFORMA.get(plataforma, plataforma)
        hora = str(tarea.get("slot") or "").strip()
        if not hora:
            valor = tarea.get("scheduled_at_local") or tarea.get("scheduled_at")
            if valor:
                try:
                    hora = datetime.fromisoformat(str(valor).replace("Z", "+00:00")).strftime("%H:%M")
                except ValueError:
                    hora = ""
        aviso = " [credenciales pendientes]" if str(tarea.get("estado", "")).casefold() == "pending_credentials" else ""
        fragmentos.append(f"{nombre} {hora or 'hora pendiente'}{aviso}")
    return " · ".join(fragmentos) if fragmentos else "sin horarios agendados"


def videos_para(fecha: date, tareas: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    datos = cargar_json(IDEAS_PATH, {"ideas": []})
    ideas = [idea for idea in datos.get("ideas", []) if isinstance(idea, dict)]
    por_proyecto: dict[str, dict[str, Any]] = {}
    for idea in ideas:
        proyecto = str(idea.get("proyecto") or "").strip()
        if proyecto:
            por_proyecto[Path(proyecto).name] = idea

    videos: list[dict[str, Any]] = []
    vistos: set[str] = set()
    for proyecto, tareas_proyecto in tareas.items():
        idea = por_proyecto.get(proyecto, {})
        videos.append(
            {
                "proyecto": proyecto,
                "titulo": str(idea.get("titulo") or titulo_de_tarea(tareas_proyecto[0], proyecto)),
                "franja": str(idea.get("franja") or ""),
                "orden": int(idea.get("orden", 99)),
                "horarios": horarios_de(tareas_proyecto),
            }
        )
        vistos.add(proyecto)

    for idea in ideas:
        if str(idea.get("estado", "")).casefold() != "completada":
            continue
        if str(idea.get("fecha_produccion") or "") != fecha.isoformat():
            continue
        proyecto = Path(str(idea.get("proyecto") or idea.get("id") or "video")).name
        if proyecto in vistos:
            continue
        videos.append(
            {
                "proyecto": proyecto,
                "titulo": str(idea.get("titulo") or proyecto),
                "franja": str(idea.get("franja") or ""),
                "orden": int(idea.get("orden", 99)),
                "horarios": "sin horarios agendados",
            }
        )
        vistos.add(proyecto)

    return sorted(videos, key=lambda video: (video["orden"], video["titulo"]))[:CUPO_DIARIO]


def oportunidades_detectadas(datos_ideas: dict[str, Any]) -> list[dict[str, Any]]:
    datos = cargar_json(OPORTUNIDADES_PATH, {"oportunidades": []})
    oportunidades = [
        oportunidad
        for oportunidad in datos.get("oportunidades", [])
        if isinstance(oportunidad, dict)
    ]
    priorizada = normalizar(datos_ideas.get("colaboracion_priorizada"))
    oportunidades.sort(
        key=lambda oportunidad: (
            normalizar(oportunidad.get("titulo")) != priorizada,
            not (oportunidad.get("vigente") and oportunidad.get("es_formal")),
            str(oportunidad.get("titulo", "")).casefold(),
        )
    )
    return oportunidades


def normalizar_texto(texto: Any) -> str:
    valor = unicodedata.normalize("NFKD", texto_utf8.limpiar_utf8(texto))
    valor = "".join(caracter for caracter in valor if not unicodedata.combining(caracter))
    return re.sub(r"\s+", " ", valor.casefold()).strip()


def datos_analytics_semanal() -> dict[str, Any]:
    try:
        import analytics_feedback

        return analytics_feedback.actualizar(dias=7)
    except Exception as error:
        try:
            datos = json.loads(ANALYTICS_PATH.read_text(encoding="utf-8", errors="replace"))
            if isinstance(datos, dict):
                avisos = list(datos.get("errores") or [])
                avisos.append(f"{type(error).__name__}: {error}")
                datos["errores"] = avisos[:10]
                return datos
        except (OSError, json.JSONDecodeError):
            pass
        return {
            "ganadores": [],
            "errores": [f"{type(error).__name__}: {error}"],
        }


def gancho_para(titulo: Any) -> str:
    buscado = normalizar_texto(titulo)
    if not buscado:
        return ""
    for ruta in sorted(ROOT_DIR.glob("*/renders/metadata.json")):
        try:
            datos = json.loads(ruta.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(datos, dict):
            continue
        for bloque in ("youtube", "tiktok", "instagram", "facebook"):
            config = datos.get(bloque)
            if not isinstance(config, dict):
                continue
            candidato = normalizar_texto(config.get("title") or config.get("titulo"))
            if candidato and candidato not in buscado and buscado not in candidato:
                continue
            gancho = texto_utf8.limpiar_utf8(
                config.get("gancho_variante") or config.get("gancho_a") or config.get("gancho")
            )
            if gancho:
                return gancho
            descripcion = texto_utf8.limpiar_utf8(config.get("description"))
            if descripcion:
                primera = next((linea.strip() for linea in descripcion.splitlines() if linea.strip()), "")
                if primera:
                    return primera
    return ""


def ajuste_temas(datos: dict[str, Any]) -> str:
    ganadores = datos.get("ganadores") or []
    primero = ganadores[0] if ganadores and isinstance(ganadores[0], dict) else {}
    palabras = [texto_utf8.limpiar_utf8(palabra) for palabra in (primero.get("keywords") or [])[:5]]
    palabras = [palabra for palabra in palabras if palabra]
    if not palabras:
        return "Sin ajuste: Analytics sin ganadores esta semana; se mantiene el peso histórico."
    return "trend_hunter.py sumó peso a: " + ", ".join(palabras)


def construir_reporte_semanal(fecha: date | str | None = None) -> str:
    fecha = fecha_objetivo(fecha)
    inicio = fecha - timedelta(days=6)
    datos = datos_analytics_semanal()
    ganadores = sorted(
        [item for item in (datos.get("ganadores") or []) if isinstance(item, dict)],
        key=lambda item: float(item.get("vistas") or 0),
        reverse=True,
    )[:3]

    lineas = [
        "AuraDrones | Reporte semanal de rendimiento",
        f"Periodo: {inicio.isoformat()} a {fecha.isoformat()}",
        "",
        "Top 3 de la semana:",
    ]
    if not ganadores:
        lineas.append("- Sin datos de YouTube Analytics en esta ventana.")
    for indice, video in enumerate(ganadores, 1):
        titulo = texto_utf8.limpiar_utf8(video.get("titulo"))[:110] or "Sin título"
        vistas = int(float(video.get("vistas") or 0))
        retencion = float(video.get("retencion_pct") or 0)
        lineas.append(f"{indice}. {titulo} | {vistas} vistas | retención {retencion:.1f}%")

    primera = ganadores[0] if ganadores else {}
    gancho = gancho_para(primera.get("titulo")) or texto_utf8.limpiar_utf8(primera.get("titulo"))
    experimentos = [item for item in (datos.get("experimentos") or []) if isinstance(item, dict)]
    mejor_ab = next((item for item in experimentos if item.get("variante") in {"A", "B"}), {})
    resumen_ab = (
        f"Variante {mejor_ab.get('variante')} | retención {float(mejor_ab.get('retencion_promedio_pct') or 0):.1f}% "
        f"en {int(mejor_ab.get('publicaciones') or 0)} publicación(es)"
        if mejor_ab
        else "sin señal suficiente"
    )
    lineas.extend(
        [
            "",
            f"Gancho ganador: {gancho or 'sin datos'}",
            f"Test A/B gancho: {resumen_ab}",
            f"Ajuste automático aplicado: {ajuste_temas(datos)}",
        ]
    )
    avisos = [texto_utf8.limpiar_utf8(aviso) for aviso in (datos.get("errores") or [])]
    if avisos:
        lineas.append(f"Aviso: {avisos[0][:180]}")

    texto = "\n".join(lineas)
    if len(texto) > LIMITE_TELEGRAM:
        texto = texto[: LIMITE_TELEGRAM - 40].rstrip() + "\n... reporte recortado por límite de Telegram"
    return texto


def enviar_reporte_semanal(fecha: date | str | None = None) -> dict[str, Any]:
    fecha = fecha_objetivo(fecha)
    texto = construir_reporte_semanal(fecha)
    datos = enviar_mensaje(texto)
    return {
        "estado": "enviado",
        "tipo": "reporte_semanal",
        "fecha": fecha.isoformat(),
        "caracteres": len(texto),
        "message_id": datos.get("result", {}).get("message_id"),
    }


def construir_resumen(fecha: date | str | None = None) -> str:
    fecha = fecha_objetivo(fecha)
    tareas = tareas_por_proyecto(fecha)
    videos = videos_para(fecha, tareas)
    datos_ideas = cargar_json(IDEAS_PATH, {"ideas": []})
    oportunidades = oportunidades_detectadas(datos_ideas)

    lineas = [
        f"AuraDrones | Resumen de produccion para {fecha.isoformat()}",
        f"Videos fabricados: {len(videos)}/{CUPO_DIARIO}",
        "",
    ]
    if not videos:
        lineas.append("No hay videos fabricados ni horarios agendados para esta fecha.")
    for indice, video in enumerate(videos, 1):
        franja = f" [{video['franja']}]" if video["franja"] else ""
        lineas.append(f"{indice}. {video['titulo']}{franja}")
        lineas.append(f"   Horarios: {video['horarios']}")

    lineas.extend(
        [
            "",
            f"Oportunidades de colaboracion detectadas: {len(oportunidades)}",
        ]
    )
    priorizada = str(datos_ideas.get("colaboracion_priorizada") or "").strip()
    if priorizada:
        lineas.append(f"Priorizada: {priorizada}")
    if not oportunidades:
        lineas.append("- Sin oportunidades detectadas.")
    for oportunidad in oportunidades:
        titulo = str(oportunidad.get("titulo") or "Sin titulo")[:100]
        url = str(oportunidad.get("url") or "").strip()
        etiqueta = "Formal" if oportunidad.get("vigente") and oportunidad.get("es_formal") else "Por verificar"
        lineas.append(f"- [{etiqueta}] {titulo}" + (f" | {url}" if url else ""))

    texto = "\n".join(lineas)
    if len(texto) > LIMITE_TELEGRAM:
        texto = texto[: LIMITE_TELEGRAM - 40].rstrip() + "\n... resumen recortado por limite de Telegram"
    return texto


def enviar_resumen(fecha: date | str | None = None) -> dict[str, Any]:
    fecha = fecha_objetivo(fecha)
    texto = construir_resumen(fecha)
    datos = enviar_mensaje(texto)
    return {
        "estado": "enviado",
        "fecha": fecha.isoformat(),
        "caracteres": len(texto),
        "message_id": datos.get("result", {}).get("message_id"),
    }


def enviar_prueba() -> dict[str, Any]:
    sello = datetime.now(ZONA).isoformat(timespec="seconds")
    datos = enviar_mensaje(f"AuraDrones | Prueba de notificacion Telegram {sello}")
    return {
        "estado": "prueba_enviada",
        "enviado_en": sello,
        "message_id": datos.get("result", {}).get("message_id"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Notifica por Telegram el resumen diario de AuraDrones.")
    parser.add_argument("--test", action="store_true", help="Envia un mensaje de prueba")
    parser.add_argument("--semanal", action="store_true", help="Envia el reporte semanal de rendimiento")
    parser.add_argument("--fecha", help="Fecha YYYY-MM-DD; por defecto mañana en America/Mexico_City")
    args = parser.parse_args(argv)

    try:
        if args.test:
            resultado = enviar_prueba()
        elif args.semanal:
            fecha = date.fromisoformat(args.fecha.strip()) if args.fecha else None
            resultado = enviar_reporte_semanal(fecha)
        else:
            fecha = date.fromisoformat(args.fecha.strip()) if args.fecha else None
            resultado = enviar_resumen(fecha)
    except (ValueError, RuntimeError, requests.RequestException) as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 2

    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
