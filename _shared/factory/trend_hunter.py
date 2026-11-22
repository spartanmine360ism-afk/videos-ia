from __future__ import annotations

import argparse
import calendar
import html
import json
import re
import subprocess
import sys
import unicodedata
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import feedparser
import requests
from ddgs import DDGS

ROOT_DIR = Path(__file__).resolve().parents[2]
FACTORY_DIR = Path(__file__).resolve().parent
PUBLISHER_DIR = ROOT_DIR / "_shared" / "publisher"
IDEAS_PATH = FACTORY_DIR / "ideas_pendientes.json"
HISTORIAL_IDEAS_PATH = FACTORY_DIR / "historial_ideas.json"
ESTADO_PATH = FACTORY_DIR / "trend_hunter_state.json"
COMERCIAL_CADA = 4
OPORTUNIDADES_PATH = FACTORY_DIR / "oportunidades_colab.json"
MINISERIE_MARCADORES = (
    "configuracion", "sensor", "comparativa", "cinematografico", "transicion",
    "sistema", "setup", "bateria", "modo", "checklist", "error",
)
MINISERIE_COMPLEJA = 2

if str(PUBLISHER_DIR) not in sys.path:
    sys.path.insert(0, str(PUBLISHER_DIR))

import analytics_feedback
import dedup_manager
import scheduler_manager

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36 AuraDronesFactory/1.0",
    "Accept-Language": "es-419,es;q=0.9,en;q=0.8",
}
STOPWORDS = {
    "con", "del", "las", "los", "una", "uno", "por", "para", "que", "como", "más", "mas", "este", "esta",
    "sus", "porque", "ante", "sin", "the", "and", "for", "with", "from", "that", "this", "how", "video",
    "videos", "drone", "drones", "fpv", "aura", "auradrones", "new", "news", "tip", "tips",
}
SITIOS = {
    "TikTok": "site:tiktok.com",
    "Instagram Reels": "site:instagram.com/reel",
    "Facebook Reels": "site:facebook.com/reel",
    "Reddit drones": "site:reddit.com/r/drones",
    "Reddit fpv": "site:reddit.com/r/fpv",
    "Reddit djimavic": "site:reddit.com/r/djimavic",
}

ANIO_ACTUAL = str(datetime.now().year)
MIN_PUNTUACION_VIRAL = 8
PESOS_ANALYTICS: list[dict[str, Any]] = analytics_feedback.cargar_ganadores()
COLAB_QUERIES = [
    f"convocatoria drones {ANIO_ACTUAL} concurso video creadores",
    f"DJI creator program {ANIO_ACTUAL} UGC TikTok",
    f"FPV challenge {ANIO_ACTUAL} TikTok Instagram Reels",
    f"drone videography contest {ANIO_ACTUAL} submissions",
    f"site:instagram.com drones challenge {ANIO_ACTUAL} reels",
    f"site:tiktok.com drone challenge {ANIO_ACTUAL} FPV",
]
COLAB_MARCADORES = (
    "convocatoria", "concurso", "challenge", "reto", "ugc", "colaboracion", "colaboración", "collab",
    "creator program", "programa de creadores", "submission", "postula", "participa", "register",
    "registration", "registro", "application is free", "portal de inscripcion",
)
COLAB_VIGENTES = ("abierta", "abierto", "inscripciones", "hasta", "deadline", "cierra", "cierre", "postula", ANIO_ACTUAL)
COLAB_VENCIDOS = (
    "cerrado", "cerrada", "finalizado", "finalizada", "2024", "2025", "winners", "ganadores",
    "celebrates", "celebra", "recibe", "results", "resultados",
)
ANIO_MINIMO = str(max(2025, int(ANIO_ACTUAL) - 1))
MESES = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}
RE_FECHA_LIMITE_ES = re.compile(
    r"(?:hasta|through|until|cierra|cierre|deadline|entre)[\s\S]{0,70}?(\d{1,2})\s+(?:de\s+)?([a-záéíóú]{3,})\s+(?:de\s+)?(\d{4})",
    re.IGNORECASE,
)
RE_FECHA_LIMITE_EN = re.compile(
    r"(?:hasta|through|until|cierra|cierre|deadline|entre)[\s\S]{0,70}?([a-z]{3,})\s+(\d{1,2}),\s*(\d{4})",
    re.IGNORECASE,
)


def fecha_limite(texto: Any) -> datetime | None:
    bruto = str(texto or "")
    for expresion, es_ingles in ((RE_FECHA_LIMITE_ES, False), (RE_FECHA_LIMITE_EN, True)):
        for coincidencia in expresion.finditer(bruto):
            if es_ingles:
                mes, dia, anio = coincidencia.groups()
            else:
                dia, mes, anio = coincidencia.groups()
            numero_mes = MESES.get(normalizar(mes)[:3])
            if not numero_mes:
                continue
            try:
                return datetime(int(anio), numero_mes, int(dia))
            except ValueError:
                continue
    return None


def convocatoria_vigente(texto: Any) -> bool:
    norm = normalizar(texto)
    if any(vencido in norm for vencido in COLAB_VENCIDOS):
        return False
    limite = fecha_limite(texto)
    if limite is not None and limite.date() < datetime.now().date() - timedelta(days=15):
        return False
    return any(vigente in norm for vigente in COLAB_VIGENTES)


def prioridad_colaboracion(oportunidad: dict[str, Any]) -> int:
    url = limpiar(oportunidad.get("url")).casefold()
    texto = normalizar(f"{oportunidad.get('titulo', '')} {oportunidad.get('resumen', '')}")
    puntos = 0
    if any(dominio in url for dominio in ("dji.com", "skypixel.com", "ipn.mx", "gob.mx", "edu.mx")):
        puntos += 8
    if any(red in url for red in ("tiktok.com", "instagram.com", "facebook.com")):
        puntos -= 2
    if "convocatoria" in texto or "concurso" in texto:
        puntos += 3
    if "submission" in texto or "premio" in texto or "premios" in texto:
        puntos += 2
    return puntos


def convocatoria_formal(oportunidad: dict[str, Any]) -> bool:
    url = limpiar(oportunidad.get("url")).casefold()
    texto = normalizar(f"{oportunidad.get('titulo', '')} {oportunidad.get('resumen', '')}")
    marcadores = (
        "convocatoria", "concurso", "contest", "postula", "inscripcion", "submission", "bases",
        "programa de creadores", "creator program", "premio", "premios", "register", "registration",
        "registro", "application is free", "portal de inscripcion",
    )
    oficial = any(dominio in url for dominio in ("dji.com", "skypixel.com", "ipn.mx", "gob.mx", "edu.mx"))
    return any(marcador in texto for marcador in marcadores) and (oficial or fecha_limite(texto) is not None)


CATEGORIAS: dict[str, dict[str, Any]] = {
    "tip": {
        "orden": 1,
        "franja": "mañana",
        "nombre": "Tip práctico DJI/FPV",
        "termino": "DJI FPV configuración oculta ajuste solución vuelo",
        "news_queries": [
            "DJI FPV configuración ajuste when:7d",
            "DJI Mini 4 Pro Avata 2 sensor checklist when:7d",
        ],
        "sitios": ["TikTok", "Reddit drones", "Reddit fpv"],
        "keywords": ["configuracion", "configura", "ajuste", "sensor", "sensores", "obstaculo", "checklist", "bateria", "vuelo", "dji", "avata", "mini", "solucion"],
        "gancho": "Tu DJI también esconde esto: {titulo}.",
        "enfoque": "Guion de 20–40 s: 0–3 s impacto con el problema real; 3–18 s ajuste o checklist en tres pasos; 18–40 s antes/después y CTA para guardar. Usa planos de configuración, pantalla, B-roll de la bóveda o mano ejecutando el cambio. Duración final 15–60 s.",
    },
    "toma": {
        "orden": 2,
        "franja": "tarde",
        "nombre": "Toma viral / movimiento cinematográfico",
        "termino": "dron toma cinematográfica truco edición reel viral",
        "news_queries": [
            "drone toma cinematográfica reel truco when:7d",
            "FPV freestyle drone cinematic shot viral when:7d",
        ],
        "sitios": ["TikTok", "Instagram Reels", "Facebook Reels"],
        "keywords": ["toma", "plano", "cinematico", "cinematográfico", "freestyle", "trick", "transicion", "transición", "movimiento", "reel", "tiktok", "viral", "camara", "cámara", "edicion", "edición"],
        "gancho": "Esta toma parece imposible: {titulo}.",
        "enfoque": "Guion de 20–45 s: 0–3 s muestra el resultado final; 3–20 s desglosa el movimiento o transición con líneas HUD y B-roll real cuando exista; 20–45 s remate con el mismo plano desde otro ángulo y CTA para comentar. Sin foto fija: cada bloque tiene movimiento. Duración final 15–60 s.",
    },
    "tech": {
        "orden": 3,
        "franja": "noche",
        "nombre": "Novedad tech / gadget / comparativa",
        "termino": "DJI dron gadget audiovisual comparativa 2026 creadores",
        "news_queries": [
            "DJI drone tecnología gadget noticia when:7d",
            "drone cámara comparativa creadores 2026 when:7d",
        ],
        "sitios": ["Instagram Reels", "Facebook Reels", "Reddit djimavic"],
        "keywords": ["tecnologia", "tecnología", "gadget", "novedad", "comparativa", "review", "camara", "cámara", "bateria", "batería", "sensor", "creadores", "2026", "dji", "audiovisual"],
        "gancho": "Esto está marcando tendencia: {titulo}.",
        "enfoque": "Guion de 20–50 s: 0–3 s dato o lanzamiento con impacto; 3–25 s comparativa rápida en dos columnas con clips propios si aplica; 25–50 s veredicto para creadores y CTA para opinar. Datos concretos, sin promesas vacías. Duración final 15–60 s.",
    },
    "comercial": {
        "orden": 4,
        "franja": "mañana",
        "nombre": "Embudo comercial Aura Drones",
        "termino": "drone servicio bienes raices inspeccion eventos FPV indoor empresa cotizacion",
        "news_queries": [
            "drone bienes raices inspeccion eventos servicio empresa when:7d",
            "FPV indoor drone inspection real estate events when:7d",
        ],
        "sitios": ["Instagram Reels", "Facebook Reels", "TikTok"],
        "keywords": ["bienes raices", "inspeccion", "eventos", "fpv indoor", "cotizacion", "empresa", "servicio", "aerial", "roof", "inmueble"],
        "gancho": "Esto le ahorra horas a {titulo}.",
        "enfoque": "Guion de 25–50 s: 0–3 s problema comercial concreto; 3–20 s aplicación real (bienes raíces, inspección, eventos o FPV indoor) con resultado medible; 20–40 s prueba visual de la bóveda o pantalla de trabajo; 40–50 s CTA de cotización con contacto profesional de Aura Drones. Sin precios inventados ni promesas de contratación. Duración final 15–60 s.",
        "cta": "Cuéntanos qué necesitas filmar y te preparamos una cotización de Aura Drones.",
    },
}


def limpiar(texto: Any) -> str:
    return re.sub(r"\s+", " ", html.unescape(str(texto or ""))).strip()


def titulo_publicacion(texto: Any) -> str:
    bruto = str(texto or "")
    valor = limpiar(bruto.splitlines()[0] if bruto.splitlines() else bruto)
    valor = re.split(
        r"\s*\|\s*(?:TikTok|Instagram|Facebook|Reddit|YouTube)(?=[A-ZÁÉÍÓÚÑ])",
        valor,
        maxsplit=1,
    )[0].strip()
    valor = re.sub(r"\s*\|\s*(?:TikTok|Instagram|Facebook|Reddit|YouTube)\s*$", "", valor)
    valor = re.sub(r"\s+on (?:Instagram|TikTok|Facebook)(?:\s*:)?", "", valor, flags=re.IGNORECASE)
    valor = re.sub(r"\s+en (?:Instagram|TikTok|Facebook)(?:\s*:)?", "", valor, flags=re.IGNORECASE)
    valor = valor.strip().strip("\"“”'")
    valor = valor.split("...")[0].strip()
    valor = re.sub(r"\s+Si buscas\b.*$", "", valor, flags=re.IGNORECASE).strip()
    valor = re.sub(r"\s+(?:el|la|los|las|un|una|the|a|an)$", "", valor, flags=re.IGNORECASE).strip()
    if len(valor) > 100:
        corte = valor.rfind(". ", 0, 100)
        if corte > 40:
            valor = valor[: corte + 1].strip()
    return valor or limpiar(texto)[:100]


def titulo_valido(candidato: dict[str, Any]) -> bool:
    titulo = limpiar(candidato.get("titulo"))
    if len(titulo) < 18:
        return False
    return not titulo.casefold().endswith(
        (" en", " de", " del", " para", " con", " a", " y", " o", " el", " la", " un", " una", " the", " for", " with")
    )


def normalizar(texto: Any) -> str:
    valor = unicodedata.normalize("NFKD", str(texto or ""))
    valor = "".join(caracter for caracter in valor if not unicodedata.combining(caracter))
    return re.sub(r"\s+", " ", valor.casefold()).strip()


def slug(texto: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "-", normalizar(texto)).strip("-") or "video"


def fecha_iso(valor: Any = None) -> str:
    fecha = datetime.now(timezone.utc)
    if isinstance(valor, datetime):
        fecha = valor
    elif isinstance(valor, (int, float)):
        fecha = datetime.fromtimestamp(valor, timezone.utc)
    elif isinstance(valor, str) and valor.strip():
        try:
            fecha = datetime.fromisoformat(valor.strip().replace("Z", "+00:00"))
        except ValueError:
            pass
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=timezone.utc)
    return fecha.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def fecha_datetime(valor: Any) -> datetime | None:
    texto = limpiar(valor)
    if not texto:
        return None
    try:
        fecha = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except ValueError:
        return None
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=timezone.utc)
    return fecha.astimezone(timezone.utc)


def plataforma_desde_url(url: str) -> str:
    texto = url.casefold()
    if "tiktok.com" in texto:
        return "TikTok"
    if "instagram.com" in texto:
        return "Instagram Reels"
    if "facebook.com" in texto or "fb.com" in texto:
        return "Facebook Reels"
    if "reddit.com" in texto:
        coincidencia = re.search(r"reddit\.com/r/([a-z0-9_]+)", texto)
        return f"Reddit r/{coincidencia.group(1)}" if coincidencia else "Reddit"
    if "youtube.com" in texto or "youtu.be" in texto:
        return "YouTube Shorts"
    return "Web"


def buscar_noticias(categoria: str, query: str) -> list[dict[str, Any]]:
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {
            "q": query,
            "hl": "es-419",
            "gl": "MX",
            "ceid": "MX:es-419",
        }
    )
    respuesta = requests.get(url, headers=HEADERS, timeout=20)
    respuesta.raise_for_status()
    feed = feedparser.parse(respuesta.content)
    resultados: list[dict[str, Any]] = []

    for entrada in feed.entries:
        titulo = limpiar(entrada.get("title"))
        enlace = limpiar(entrada.get("link"))
        if not titulo or not enlace:
            continue

        fuente = limpiar(getattr(entrada.get("source"), "title", "")) or "Google News"
        sufijo = f" - {fuente}"
        if titulo.endswith(sufijo):
            titulo = titulo[: -len(sufijo)].strip()

        publicado = limpiar(entrada.get("published"))
        if entrada.get("published_parsed"):
            publicado = fecha_iso(datetime.fromtimestamp(calendar.timegm(entrada.published_parsed), timezone.utc))

        resultados.append(
            {
                "titulo": titulo,
                "url": enlace,
                "resumen": limpiar(entrada.get("summary")),
                "fuente": f"Google News · {fuente}",
                "plataforma": "Google News",
                "publicado_en": publicado,
                "metricas": {},
                "categoria": categoria,
            }
        )
    return resultados


def buscar_ddgs(categoria: str, sitio: str, termino: str) -> list[dict[str, Any]]:
    query = f"{SITIOS[sitio]} {termino}"
    crudos = DDGS().text(query, max_results=6)
    resultados: list[dict[str, Any]] = []

    for item in crudos:
        titulo = titulo_publicacion(item.get("title"))
        enlace = limpiar(item.get("href"))
        resumen = limpiar(item.get("body"))
        if not titulo or not enlace:
            continue
        resultados.append(
            {
                "titulo": titulo,
                "url": enlace,
                "resumen": resumen,
                "fuente": f"DuckDuckGo · {sitio}",
                "plataforma": plataforma_desde_url(enlace),
                "publicado_en": "",
                "metricas": {},
                "categoria": categoria,
            }
        )
    return resultados


def buscar_youtube_shorts(categoria: str, termino: str) -> list[dict[str, Any]]:
    comando = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--dump-single-json",
        "--skip-download",
        "--no-warnings",
        "--playlist-end",
        "8",
        f"ytsearch8:{termino} short youtube shorts",
    ]
    proceso = subprocess.run(
        comando,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=45,
    )
    if proceso.returncode != 0:
        raise RuntimeError((proceso.stderr or "yt-dlp sin salida").strip()[:300])

    datos = json.loads(proceso.stdout or "{}")
    resultados: list[dict[str, Any]] = []

    for entrada in datos.get("entries", []):
        titulo = limpiar(entrada.get("title"))
        enlace = limpiar(entrada.get("webpage_url") or entrada.get("url"))
        duracion = entrada.get("duration")
        if not titulo or not enlace or len(titulo) < 12:
            continue
        if isinstance(duracion, (int, float)) and duracion > 180:
            continue

        resultados.append(
            {
                "titulo": titulo,
                "url": enlace,
                "resumen": limpiar(entrada.get("description")),
                "fuente": "YouTube Shorts · yt-dlp --dump-single-json",
                "plataforma": "YouTube Shorts",
                "publicado_en": fecha_iso(entrada.get("timestamp")),
                "metricas": {
                    "views": int(entrada.get("view_count") or 0),
                    "likes": int(entrada.get("like_count") or 0),
                    "duration": int(duracion or 0),
                },
                "categoria": categoria,
            }
        )
    return resultados


_RECOLECTA_CACHE: dict[str, Any] = {"ts": 0.0, "data": None}


def recolectar(ttl_segundos: int = 900, forzar: bool = False) -> tuple[list[dict[str, Any]], list[str]]:
    import time
    ahora = time.time()
    if not forzar and _RECOLECTA_CACHE["data"] is not None and (ahora - float(_RECOLECTA_CACHE["ts"])) < ttl_segundos:
        return _RECOLECTA_CACHE["data"]
    candidatos: list[dict[str, Any]] = []
    errores: list[str] = []

    for categoria, config in CATEGORIAS.items():
        for query in config["news_queries"]:
            try:
                candidatos.extend(buscar_noticias(categoria, query))
            except Exception as error:
                errores.append(f"{categoria}/feedparser: {type(error).__name__}: {error}")

        try:
            candidatos.extend(buscar_youtube_shorts(categoria, config["termino"]))
        except Exception as error:
            errores.append(f"{categoria}/yt-dlp: {type(error).__name__}: {error}")

        for sitio in config["sitios"]:
            try:
                candidatos.extend(buscar_ddgs(categoria, sitio, config["termino"]))
            except Exception as error:
                errores.append(f"{categoria}/ddgs/{sitio}: {type(error).__name__}: {error}")
        # si ya hay suficientes candidatos de calidad para esta corrida, evita exceso de consultas
        buenos = 0
        for candidato in candidatos:
            categoria_c = str(candidato.get("categoria") or "")
            if categoria_c not in CATEGORIAS:
                continue
            try:
                if puntuar(candidato, categoria_c) >= 16:
                    buenos += 1
            except Exception:
                continue
        if buenos >= 12:
            break

    resultado = (candidatos, errores)
    _RECOLECTA_CACHE.update({"ts": __import__("time").time(), "data": resultado})
    return resultado


def tokens(texto: Any) -> set[str]:
    return {palabra for palabra in re.findall(r"[a-z0-9]{3,}", normalizar(texto)) if palabra not in STOPWORDS}


def es_repetido(candidato: dict[str, Any], usados: list[str] | None = None) -> bool:
    return dedup_manager.es_tema_repetido(candidato.get("titulo"), candidato.get("resumen"))


def puntuar(candidato: dict[str, Any], categoria: str) -> float:
    config = CATEGORIAS[categoria]
    texto = normalizar(f"{candidato.get('titulo', '')} {candidato.get('resumen', '')}")
    puntos = sum(3 for palabra in config["keywords"] if normalizar(palabra) in texto)

    plataforma = candidato.get("plataforma")
    if plataforma == "YouTube Shorts":
        puntos += 5
    elif plataforma in {"TikTok", "Instagram Reels", "Facebook Reels"}:
        puntos += 4
    elif str(plataforma).startswith("Reddit"):
        puntos += 3
    elif plataforma == "Google News":
        puntos += 2

    metricas = candidato.get("metricas") if isinstance(candidato.get("metricas"), dict) else {}
    vistas = int(metricas.get("views") or 0)
    if vistas >= 100000:
        puntos += 5
    elif vistas >= 10000:
        puntos += 3

    duracion = int(metricas.get("duration") or 0)
    if 0 < duracion <= 60:
        puntos += 3

    if any(palabra in texto for palabra in ("viral", "tendencia", "trend", "reel", "short", "truco")):
        puntos += 2

    fecha = fecha_datetime(candidato.get("publicado_en"))
    if fecha is not None:
        puntos += max(0, 8 - max(0, (datetime.now(timezone.utc) - fecha).days))

    anios = {int(anio) for anio in re.findall(r"\b(20\d{2})\b", texto)}
    if any(anio < int(ANIO_MINIMO) for anio in anios):
        puntos -= 6
    elif int(ANIO_ACTUAL) in anios:
        puntos += 4

    longitud = len(limpiar(candidato.get("titulo")))
    if 28 <= longitud <= 110:
        puntos += 2

    texto_tokens = tokens(texto)
    for ganador in PESOS_ANALYTICS:
        claves = {normalizar(palabra) for palabra in ganador.get("keywords", [])}
        if claves & texto_tokens:
            puntos += round(float(ganador.get("peso") or 0) * 1.2, 1)
    return puntos


def candidato_fallback(categoria: str, usados: list[str] | None = None) -> dict[str, Any]:
    config = CATEGORIAS[categoria]
    base = config["termino"]
    titulo = f"{base[0].upper()}{base[1:]}: qué revisar antes de volar en {ANIO_ACTUAL}"
    intento = 2
    while es_repetido({"titulo": titulo, "resumen": config["enfoque"]}) and intento < 20:
        titulo = f"{base[0].upper()}{base[1:]}: {intento} señales para decidir mejor en {ANIO_ACTUAL}"
        intento += 1

    return {
        "titulo": titulo,
        "url": "",
        "resumen": config["enfoque"],
        "fuente": "Consulta semilla (sin resultados externos explotables)",
        "plataforma": "Semilla local",
        "publicado_en": "",
        "metricas": {},
        "categoria": categoria,
    }


def crear_ganchos_ab(titulo: str, gancho: str = "") -> dict[str, str]:
    base = limpiar(gancho) or limpiar(titulo)
    return {
        "gancho_a": f"El error de {base.rstrip('.')} que casi nadie ve.",
        "gancho_b": f"{base.rstrip('.')}: resultado directo en 15 segundos.",
    }


def complejidad_tema(idea: dict[str, Any]) -> int:
    texto = normalizar(f"{idea.get('titulo', '')} {idea.get('resumen', '')}")
    return sum(1 for marcador in MINISERIE_MARCADORES if marcador in texto)


def aplicar_miniseries(ideas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Desdobla el tema raíz en una trilogía coherente de 3 episodios."""
    if len(ideas) < 2:
        return ideas

    candidatos = [i for i, idea in enumerate(ideas) if not idea.get("es_comercial") and not idea.get("es_colaboracion") and idea.get("tipo") != "colaboracion"]
    pool = candidatos or list(range(len(ideas)))
    indice_base = max(pool, key=lambda indice: (complejidad_tema(ideas[indice]), float(ideas[indice].get("puntuacion_viral", 0) or 0)))
    raiz = ideas[indice_base]
    tiene_marcador = any(m in normalizar(f"{raiz.get('titulo','')} {raiz.get('enfoque','')} {raiz.get('resumen','')}") for m in MINISERIE_MARCADORES)
    if not (tiene_marcador or len(ideas) >= 3):
        return ideas

    total = 3
    serie_id = slug(raiz.get("titulo") or "serie-aura")[:38]
    titulo_base = limpiar(raiz.get("titulo") or "Tema clave")
    tema_corto = titulo_base.replace(" — EPISODIO", "").strip(" -:|")

    # Franjas/orden: conserva las de las primeras 3 ideas; si faltan, crea defaults.
    slots = []
    for i in range(total):
        src = ideas[i] if i < len(ideas) else ideas[-1]
        slots.append({
            "franja": src.get("franja", ["mañana", "tarde", "noche"][i]),
            "orden": src.get("orden", i + 1),
            "fecha_objetivo": src.get("fecha_objetivo", ""),
        })

    episodios_cfg = [
        {
            "ep": 1,
            "titulo": f"{tema_corto} — EPISODIO 1/3: El error oculto",
            "gancho": f"EPISODIO 1/3: el error en {tema_corto} que casi nadie detecta a tiempo.",
            "gancho_a": f"El error oculto en {tema_corto} que te está costando resultados.",
            "gancho_b": f"{tema_corto}: el fallo que debes detectar antes de volar.",
            "enfoque": (
                f"Diagnóstico claro de qué falla o qué está oculto en {tema_corto}. "
                "Muestra la señal de alerta, por qué pasa y el riesgo real. "
                "Usa tarjeta central de debate rápido Opción A vs Opción B."
            ),
            "adelanto": f"En el Episodio 2 te muestro el ajuste exacto que lo soluciona.",
            "arco": "Diagnóstico y alerta",
        },
        {
            "ep": 2,
            "titulo": f"{tema_corto} — EPISODIO 2/3: El ajuste paso a paso",
            "gancho": f"EPISODIO 2/3: el ajuste exacto para resolver {tema_corto} en 3 pasos.",
            "gancho_a": f"3 pasos concretos para corregir {tema_corto} sin complicarte.",
            "gancho_b": f"Ajuste exacto para {tema_corto}: hazlo así y evita el error.",
            "enfoque": (
                f"Técnica paso a paso para corregir {tema_corto}: 3 pasos accionables, "
                "configuración o ejecución precisa y verificación rápida. "
                "Usa tarjeta central de debate rápido Opción A vs Opción B."
            ),
            "adelanto": "Pero falta un detalle crítico en vuelo real que vemos en el Episodio 3.",
            "arco": "Ajuste y técnica",
        },
        {
            "ep": 3,
            "titulo": f"{tema_corto} — EPISODIO 3/3: Prueba real y veredicto",
            "gancho": f"EPISODIO 3/3: prueba real de {tema_corto}, antes y después.",
            "gancho_a": f"Prueba real de {tema_corto}: ¿cambio real o solo teoría?",
            "gancho_b": f"Antes vs después en {tema_corto}: el veredicto final en campo.",
            "enfoque": (
                f"Resultado en campo para {tema_corto}: comparativa antes/después, "
                "veredicto final y recomendación práctica. "
                "Cierra con debate Opción A vs Opción B para comentar."
            ),
            "adelanto": "Cierre de la miniserie: comenta Opción A o Opción B y comparte tu resultado.",
            "arco": "Prueba real y veredicto",
        },
    ]

    resultado: list[dict[str, Any]] = []
    for i, cfg in enumerate(episodios_cfg):
        base = dict(raiz)
        slot = slots[i]
        capitulo = cfg["ep"]
        base.update({
            "id": f"{serie_id}-ep{capitulo}",
            "serie_id": serie_id,
            "episodio": capitulo,
            "total_episodios": total,
            "arco": f"Miniserie {serie_id}: {cfg['arco']}",
            "titulo": cfg["titulo"],
            "gancho": cfg["gancho"],
            "gancho_a": cfg["gancho_a"],
            "gancho_b": cfg["gancho_b"],
            "enfoque": cfg["enfoque"],
            "adelanto": cfg["adelanto"],
            "franja": slot["franja"],
            "orden": slot["orden"],
            "fecha_objetivo": slot.get("fecha_objetivo", ""),
            "detonador_tipo": "opcion_a_b",
            "debate_a": "Opción A: método actual",
            "debate_b": "Opción B: ajuste propuesto",
            "miniserie_tema_raiz": tema_corto,
        })
        # evita que dedup marque episodios como idénticos
        base["resumen"] = f"{limpiar(raiz.get('resumen',''))} [EP{capitulo}/3 {cfg['arco']}]".strip()
        resultado.append(base)

    # Conserva embudo comercial/colaboraciones sin romper la trilogía
    extras = []
    for idx, idea in enumerate(ideas):
        if idx == indice_base:
            continue
        if idea.get("es_comercial") or idea.get("es_colaboracion") or idea.get("tipo") == "colaboracion":
            copia = dict(idea)
            extras.append(copia)
    # Inserta extras después de la trilogía (la fábrica toma cupo diario; quedan en cola)
    for copia in extras:
        copia["orden"] = len(resultado) + 1
        resultado.append(copia)

    for i, idea in enumerate(resultado, start=1):
        idea["orden"] = i
    return resultado



def construir_idea(categoria: str, candidato: dict[str, Any]) -> dict[str, Any]:
    config = CATEGORIAS[categoria]
    titulo = limpiar(candidato.get("titulo"))
    gancho = config["gancho"].format(titulo=titulo)
    return {
        "orden": config["orden"],
        "franja": config["franja"],
        "id": f"{categoria}-{slug(titulo)[:44]}",
        "categoria": config["nombre"],
        "titulo": titulo,
        "gancho": gancho,
        "enfoque": config["enfoque"],
        "detonador_tipo": "opcion_a_b",
        "debate_a": "Opción A · método actual",
        "debate_b": "Opción B · cambio propuesto",
        **crear_ganchos_ab(titulo, gancho),
        "fuente": limpiar(candidato.get("fuente")),
        "url": limpiar(candidato.get("url")),
        "plataforma": limpiar(candidato.get("plataforma")),
        "resumen": limpiar(candidato.get("resumen"))[:500],
        "metricas": candidato.get("metricas") if isinstance(candidato.get("metricas"), dict) else {},
        "puntuacion_viral": round(puntuar(candidato, categoria), 1),
        "publicado_en": limpiar(candidato.get("publicado_en")),
        "estado": "pendiente",
        "intentos": 0,
        "creado_en": fecha_iso(),
    }


def buscar_colaboraciones() -> tuple[list[dict[str, Any]], list[str]]:
    crudos: list[dict[str, Any]] = []
    errores: list[str] = []
    for query in COLAB_QUERIES:
        try:
            crudos.extend(DDGS().text(query, max_results=6))
        except Exception as error:
            errores.append(f"ddgs/colab: {type(error).__name__}: {error}")

    urls_vencidas: set[str] = set()
    for item in crudos:
        url = limpiar(item.get("href"))
        texto = normalizar(f"{titulo_publicacion(item.get('title'))} {limpiar(item.get('body'))}")
        limite = fecha_limite(texto)
        if (limite is not None and limite.date() < datetime.now().date() - timedelta(days=15)) or any(
            vencido in texto for vencido in COLAB_VENCIDOS
        ):
            urls_vencidas.add(url)

    oportunidades: list[dict[str, Any]] = []
    urls_vistas: set[str] = set()
    for item in crudos:
        titulo = titulo_publicacion(item.get("title"))
        url = limpiar(item.get("href"))
        resumen = limpiar(item.get("body"))
        texto = normalizar(f"{titulo} {resumen}")
        if len(titulo) < 18 or not url or url in urls_vistas or url in urls_vencidas:
            continue
        if not any(marcador in texto for marcador in COLAB_MARCADORES):
            continue
        if not convocatoria_vigente(texto):
            continue
        urls_vistas.add(url)
        oportunidad = {
            "titulo": titulo[:120],
            "url": url,
            "resumen": resumen[:500],
            "fuente": "DuckDuckGo · colaboraciones/UGC/concursos/retos",
            "plataforma": plataforma_desde_url(url),
            "motivo": "Convocatoria, colaboración, UGC o reto detectado en búsqueda abierta.",
            "accion": "Verificar fechas, bases y titularidad de la marca antes de publicar; citar la fuente oficial.",
            "vigente": True,
            "detectado_en": fecha_iso(),
            "metricas": {},
        }
        oportunidad["es_formal"] = convocatoria_formal(oportunidad)
        oportunidades.append(oportunidad)
    return oportunidades, errores


def guardar_oportunidades(oportunidades: list[dict[str, Any]], errores: list[str]) -> None:
    guardar(
        {
            "generado_en": fecha_iso(),
            "fuentes_consultadas": COLAB_QUERIES,
            "total": len(oportunidades),
            "errores_fuente": errores[:30],
            "oportunidades": oportunidades,
        },
        OPORTUNIDADES_PATH,
    )


def archivar_ideas() -> None:
    if not IDEAS_PATH.is_file():
        return
    try:
        actuales = json.loads(IDEAS_PATH.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError:
        return
    historial: dict[str, Any]
    if HISTORIAL_IDEAS_PATH.is_file():
        try:
            historial = json.loads(HISTORIAL_IDEAS_PATH.read_text(encoding="utf-8", errors="replace"))
        except json.JSONDecodeError:
            historial = {"ideas": []}
    else:
        historial = {"ideas": []}
    ideas = historial.get("ideas", [])
    if not isinstance(ideas, list):
        ideas = []
    vistas = {normalizar(idea.get("titulo")) for idea in ideas if isinstance(idea, dict)}
    for idea in actuales.get("ideas", []):
        if not isinstance(idea, dict):
            continue
        titulo = normalizar(idea.get("titulo"))
        if not titulo or titulo in vistas:
            continue
        idea["archivado_en"] = fecha_iso()
        ideas.append(idea)
        vistas.add(titulo)
    historial["ideas"] = ideas
    historial["actualizado_en"] = fecha_iso()
    guardar(historial, HISTORIAL_IDEAS_PATH)


def idea_colaboracion(oportunidad: dict[str, Any]) -> dict[str, Any]:
    titulo = limpiar(oportunidad.get("titulo"))
    if len(titulo) < 18:
        titulo = f"Convocatoria activa para creadores de drones: {titulo}"[:120]
    return {
        "orden": 2,
        "franja": "tarde",
        "id": f"colab-{slug(titulo)[:44]}",
        "categoria": "Colaboración / convocatoria activa",
        "titulo": titulo,
        "gancho": f"Convocatoria real para creadores de drones: {titulo}.",
        "enfoque": "Guion de 20–45 s: 0–3 s anuncia la convocatoria con fecha o requisito concreto; 3–22 s muestra cómo participar en tres pasos; 22–45 s cierra con CTA y por qué importa sumarse. Usa solo datos comprobables de la fuente. Duración final 15–60 s.",
        "fuente": limpiar(oportunidad.get("fuente")),
        "url": limpiar(oportunidad.get("url")),
        "plataforma": limpiar(oportunidad.get("plataforma")),
        "resumen": limpiar(oportunidad.get("resumen"))[:500],
        "metricas": oportunidad.get("metricas") if isinstance(oportunidad.get("metricas"), dict) else {},
        "puntuacion_viral": 10.0,
        "publicado_en": limpiar(oportunidad.get("detectado_en")),
        "estado": "pendiente",
        "intentos": 0,
        "creado_en": fecha_iso(),
        "es_colaboracion": True,
        "prioridad_colaboracion": True,
    }


def aplicar_colaboracion(
    seleccionados: list[dict[str, Any]], oportunidades: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    for oportunidad in sorted(oportunidades, key=prioridad_colaboracion, reverse=True):
        if not oportunidad.get("vigente") or not oportunidad.get("es_formal"):
            continue
        if es_repetido({"titulo": oportunidad.get("titulo"), "resumen": oportunidad.get("resumen")}):
            continue
        idea = idea_colaboracion(oportunidad)
        for indice, seleccionado in enumerate(seleccionados):
            if seleccionado.get("orden") == 2:
                seleccionados[indice] = idea
                return seleccionados, idea
    return seleccionados, None


def elegir(
    candidatos: list[dict[str, Any]], usados: list[str] | None = None, oportunidades: list[dict[str, Any]] | None = None
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    seleccionados: list[dict[str, Any]] = []
    titulos_previos = list(usados or [])
    urls_vistas: set[str] = set()
    titulos_vistos: set[str] = set()

    for categoria in sorted(CATEGORIAS, key=lambda clave: CATEGORIAS[clave]["orden"]):
        if categoria == "comercial":
            continue
        base_pool = [
            candidato
            for candidato in candidatos
            if candidato.get("categoria") == categoria and titulo_valido(candidato)
        ]
        pool = [candidato for candidato in base_pool if puntuar(candidato, categoria) >= MIN_PUNTUACION_VIRAL]
        if not pool:
            pool = base_pool
        pool.sort(key=lambda candidato: puntuar(candidato, categoria), reverse=True)

        elegido = None
        for candidato in pool:
            url = limpiar(candidato.get("url"))
            titulo = limpiar(candidato.get("titulo"))
            if url and url in urls_vistas:
                continue
            if normalizar(titulo) in titulos_vistos:
                continue
            if es_repetido(candidato):
                continue
            elegido = candidato
            break

        if elegido is None:
            elegido = candidato_fallback(categoria, titulos_previos)

        titulo_elegido = limpiar(elegido.get("titulo"))
        urls_vistas.add(limpiar(elegido.get("url")))
        titulos_vistos.add(normalizar(titulo_elegido))
        titulos_previos.append(titulo_elegido)
        seleccionados.append(construir_idea(categoria, elegido))

    seleccionados, colaboracion = aplicar_colaboracion(seleccionados, oportunidades or [])
    return aplicar_miniseries(seleccionados), colaboracion


def cargar_contador() -> int:
    if not ESTADO_PATH.is_file():
        return 0
    try:
        datos = json.loads(ESTADO_PATH.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return 0
    try:
        return max(0, int(datos.get("videos_generados", 0)))
    except (TypeError, ValueError):
        return 0


def guardar_contador(valor: int) -> None:
    ESTADO_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporal = ESTADO_PATH.with_name(ESTADO_PATH.name + ".tmp")
    temporal.write_text(
        json.dumps(
            {"videos_generados": max(0, int(valor)), "comercial_cada": COMERCIAL_CADA},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    temporal.replace(ESTADO_PATH)


def incluir_comercial(inicio: int, cantidad: int) -> list[int]:
    indices: list[int] = []
    for relativo in range(cantidad):
        if (inicio + relativo + 1) % COMERCIAL_CADA == 0:
            indices.append(relativo)
    return indices


def aplicar_embudo_comercial(
    seleccionados: list[dict[str, Any]],
    candidatos: list[dict[str, Any]],
    usados: list[str] | None = None,
    inicio: int = 0,
) -> tuple[list[dict[str, Any]], list[int]]:
    posiciones = incluir_comercial(inicio, len(seleccionados))
    if not posiciones:
        return seleccionados, []

    titulos_previos = list(usados or [])
    base_pool = [
        candidato
        for candidato in candidatos
        if candidato.get("categoria") == "comercial" and titulo_valido(candidato)
    ]
    pool = [
        candidato
        for candidato in base_pool
        if puntuar(candidato, "comercial") >= MIN_PUNTUACION_VIRAL
    ] or base_pool
    pool.sort(key=lambda candidato: puntuar(candidato, "comercial"), reverse=True)

    elegido = next(
        (
            candidato
            for candidato in pool
            if normalizar(limpiar(candidato.get("titulo"))) not in titulos_previos
            and not es_repetido(candidato)
        ),
        None,
    )
    if elegido is None:
        elegido = candidato_fallback("comercial", titulos_previos)

    idea = construir_idea("comercial", elegido)
    idea["es_comercial"] = True
    idea["cta_tipo"] = "cotizacion"
    idea["cta"] = CATEGORIAS["comercial"]["cta"]

    resultado = list(seleccionados)
    for posicion in posiciones:
        reemplazo = 1 if (inicio + posicion) // COMERCIAL_CADA % 2 == 0 else 2
        indice = min(reemplazo, len(resultado) - 1)
        resultado[indice] = {**idea, "orden": resultado[indice].get("orden", indice + 1)}
    return resultado, posiciones


def guardar(datos: dict[str, Any], destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_name(destino.name + ".tmp")
    temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporal.replace(destino)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Genera 3 ideas reales para la fábrica diaria.")
    parser.add_argument("--output", default=str(IDEAS_PATH), help="Ruta de ideas_pendientes.json")
    parser.add_argument("--fecha", help="Fecha objetivo YYYY-MM-DD; por defecto mañana en America/Mexico_City")
    parser.add_argument("--dry-run", action="store_true", help="Muestra el resultado sin escribir el archivo")
    args = parser.parse_args(argv)

    global PESOS_ANALYTICS
    if not args.dry_run:
        datos_analytics = analytics_feedback.actualizar()
        PESOS_ANALYTICS = analytics_feedback.cargar_ganadores()
        print(
            f"Analytics: {datos_analytics['total_ganadores']} temas ganadores | "
            f"avisos={len(datos_analytics['errores'])}"
        )

    if args.fecha:
        try:
            fecha = datetime.strptime(args.fecha, "%Y-%m-%d").date()
        except ValueError:
            print("[ERROR] --fecha debe usar YYYY-MM-DD", file=sys.stderr)
            return 1
    else:
        fecha = (scheduler_manager.ahora_local() + timedelta(days=1)).date()

    dedup_manager.indexar(escribir=not args.dry_run)
    oportunidades, errores_colab = buscar_colaboraciones()
    if not args.dry_run:
        guardar_oportunidades(oportunidades, errores_colab)

    candidatos, errores = recolectar()
    contador_inicial = cargar_contador()
    ideas, colaboracion = elegir(candidatos, oportunidades=oportunidades)
    ideas, posiciones_comercial = aplicar_embudo_comercial(
        ideas, candidatos, inicio=contador_inicial
    )
    if not args.dry_run:
        guardar_contador(contador_inicial + len(ideas))
    datos = {
        "generado_en": fecha_iso(),
        "fecha_objetivo": fecha.isoformat(),
        "zona_horaria": "America/Mexico_City",
        "fuentes_consultadas": [
            "Google News RSS (feedparser)",
            "DuckDuckGo (ddgs)",
            "YouTube Shorts (yt-dlp --dump-single-json)",
            "YouTube Analytics (yt-analytics.readonly)",
            "DuckDuckGo colaboraciones/UGC/concursos/retos",
            "requests",
        ],
        "errores_fuente": (errores + errores_colab)[:30],
        "colaboraciones_detectadas": len(oportunidades),
        "colaboracion_priorizada": limpiar(colaboracion.get("titulo")) if colaboracion else "",
        "embudo_comercial_posiciones": posiciones_comercial,
        "ideas": ideas,
    }

    if args.dry_run:
        print(json.dumps(datos, ensure_ascii=False, indent=2))
        return 0

    archivar_ideas()
    guardar(datos, Path(args.output))
    print(f"Ideas escritas: {args.output}")
    for idea in ideas:
        marca = " [COTIZACION]" if idea.get("es_comercial") else ""
        print(f"- [{idea['franja']}] {idea['titulo']}{marca}")
    if posiciones_comercial:
        print(f"Embudo comercial Aura Drones incluido en {len(posiciones_comercial)} video(s) de 4.")
    series = {str(idea.get("serie_id")) for idea in ideas if idea.get("serie_id")}
    if series:
        print(f"Miniseries programadas: {', '.join(sorted(series))}")
    if colaboracion:
        print(f"Colaboración priorizada: {colaboracion['titulo']}")
    todos_errores = errores + errores_colab
    if todos_errores:
        print(f"Fuentes con error: {len(todos_errores)} (ver 'errores_fuente' en el JSON)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
