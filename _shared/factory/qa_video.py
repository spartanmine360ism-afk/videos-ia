from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from html import unescape
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT_DIR = Path(__file__).resolve().parents[2]
FACTORY_DIR = Path(__file__).resolve().parent
if str(FACTORY_DIR) not in sys.path:
    sys.path.insert(0, str(FACTORY_DIR))

import estilos_video

ANCHO = 1080
ALTO = 1920
DURACION_MINIMA = 15.0
DURACION_MAXIMA = 60.0
LIMITE_INFERIOR_VACIO = 1320
ZONAS: dict[str, dict[str, int]] = {
    "top": {"left": 80, "right": 930, "top": 200, "bottom": 340},
    "main": {"left": 80, "right": 930, "top": 380, "bottom": 1260},
}
PALETAS: dict[str, dict[str, str]] = {
    "tips": {"accent": "#00E5FF", "accent_2": "#F4FBFF", "ground": "#0B111A", "surface": "#101A27", "ink": "#F4FBFF", "font_display": "Outfit"},
    "fpv": {"accent": "#FF6B00", "accent_2": "#FFD166", "ground": "#0D0D0F", "surface": "#171216", "ink": "#FFF7ED", "font_display": "Outfit"},
    "cine": {"accent": "#10B981", "accent_2": "#FBBF24", "ground": "#0F172A", "surface": "#111C32", "ink": "#ECFDF5", "font_display": "Space Grotesk"},
    "tech": {"accent": "#8B5CF6", "accent_2": "#EC4899", "ground": "#090D16", "surface": "#12142A", "ink": "#F5F3FF", "font_display": "Outfit"},
}
MARCADORES_ZONA: dict[str, tuple[str, ...]] = {
    "top": ("caption", "subtitle", "subtitulo", "subtit", "karaoke", "step", "badge", "category", "categoria", "etiqueta", "progress", "dot", "pill"),
    "main": ("title", "hero", "headline", "metric", "card", "copy", "kicker", "status", "cta", "question", "hint", "debate", "svg", "drone", "dial", "trajectory"),
}
FRAMES_QA = (0.03, 0.15, 0.50, 0.85)

VOID_TAGS = {"area", "base", "br", "circle", "col", "embed", "hr", "img", "input", "link", "meta", "path", "rect", "source", "track", "wbr"}
RE_SILENCIO = re.compile(r"silence_(start|end):\s*([0-9]+(?:\.[0-9]+)?)")
RE_POSICION_ASS = re.compile(r"\\pos\(([-\d.]+),\s*([-\d.]+)\)")
RE_ALINEACION_ASS = re.compile(r"\\an([1-9])")
RE_ETIQUETA = re.compile(r"<(/?)([a-zA-Z][\w-]*)\b([^>]*)>", re.DOTALL)
RE_ATRIBUTO = re.compile(r"([:\w-]+)\s*=\s*([\"'])(.*?)\2", re.DOTALL)


def limpiar(texto: Any) -> str:
    return re.sub(r"\s+", " ", str(texto or "")).strip()


def normalizar(texto: Any) -> str:
    return re.sub(r"[^a-z]", "", str(texto or "").casefold())


def resolver_herramienta(nombre: str) -> str:
    ruta = shutil.which(nombre)
    if not ruta:
        raise RuntimeError(f"No se encontró {nombre} en PATH")
    return ruta


def ejecutar(args: list[str], timeout: int = 180) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def ruta_video(proyecto: Path, video: Path | None = None) -> Path:
    if video is not None:
        return video if video.is_absolute() else proyecto / video
    renders = proyecto / "renders"
    metadata_path = renders / "metadata.json"
    if metadata_path.is_file():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8", errors="replace"))
            nombre = limpiar(metadata.get("video"))
            if nombre:
                candidato = renders / nombre
                if candidato.is_file():
                    return candidato
        except (OSError, json.JSONDecodeError):
            pass
    mp4s = [ruta for ruta in renders.glob("*.mp4") if ruta.is_file()]
    if not mp4s:
        raise FileNotFoundError(f"No hay MP4 en {renders}")
    return max(mp4s, key=lambda ruta: ruta.stat().st_mtime)


def probe_video(video: Path) -> tuple[dict[str, Any], list[str]]:
    problemas: list[str] = []
    try:
        ffprobe = resolver_herramienta("ffprobe")
        proceso = ejecutar(
            [ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(video)]
        )
    except (OSError, subprocess.SubprocessError, RuntimeError) as error:
        return {}, [f"ffprobe no disponible o falló: {error}"]

    if proceso.returncode != 0:
        return {}, [f"ffprobe falló: {limpiar(proceso.stderr)[:300]}"]
    try:
        datos = json.loads(proceso.stdout or "{}")
    except json.JSONDecodeError as error:
        return {}, [f"salida JSON de ffprobe inválida: {error}"]

    streams = datos.get("streams", [])
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
    formato = datos.get("format", {})
    duracion = 0.0
    for valor in (video_stream.get("duration"), formato.get("duration")):
        try:
            duracion = float(valor)
            if duracion > 0:
                break
        except (TypeError, ValueError):
            continue

    ancho = int(video_stream.get("width") or 0)
    alto = int(video_stream.get("height") or 0)
    if (ancho, alto) != (ANCHO, ALTO):
        problemas.append(f"resolución {ancho}x{alto}, esperada {ANCHO}x{ALTO}")
    if not DURACION_MINIMA <= duracion <= DURACION_MAXIMA:
        problemas.append(
            f"duración {duracion:.2f}s fuera del rango {DURACION_MINIMA:.0f}-{DURACION_MAXIMA:.0f}s"
        )
    if not str(video_stream.get("codec_name") or ""):
        problemas.append("ffprobe no reportó codec de video")

    audio: dict[str, Any] = {
        "presente": bool(audio_streams),
        "codec": limpiar(audio_streams[0].get("codec_name")) if audio_streams else "",
        "canales": int(audio_streams[0].get("channels") or 0) if audio_streams else 0,
        "frecuencia": int(audio_streams[0].get("sample_rate") or 0) if audio_streams else 0,
    }
    if not audio["presente"]:
        problemas.append("sin pista de audio")
    elif not audio["codec"] or audio["canales"] <= 0 or audio["frecuencia"] <= 0:
        problemas.append(f"audio inválido: {audio}")

    return {
        "ancho": ancho,
        "alto": alto,
        "duracion": round(duracion, 3),
        "codec_video": limpiar(video_stream.get("codec_name")),
        "audio": audio,
    }, problemas


def analizar_silencio_inicial(video: Path, duracion: float) -> tuple[float | None, list[str]]:
    try:
        ffmpeg = resolver_herramienta("ffmpeg")
        proceso = ejecutar(
            [
                ffmpeg,
                "-hide_banner",
                "-nostats",
                "-i",
                str(video),
                "-af",
                "silencedetect=noise=-45dB:d=0.3",
                "-f",
                "null",
                "-",
            ]
        )
    except (OSError, subprocess.SubprocessError, RuntimeError) as error:
        return None, [f"ffmpeg no disponible o falló al analizar silencio: {error}"]

    salida = (proceso.stderr or "") + "\n" + (proceso.stdout or "")
    if proceso.returncode != 0 and not RE_SILENCIO.search(salida):
        return None, [f"ffmpeg falló al analizar silencio: {limpiar(proceso.stderr)[:300]}"]
    eventos: list[tuple[str, float]] = [
        (tipo, float(valor)) for tipo, valor in RE_SILENCIO.findall(salida)
    ]
    if not eventos:
        return 0.0, []

    primer_tipo, primer_valor = eventos[0]
    if primer_tipo != "start" or primer_valor > 0.05:
        return 0.0, []

    segundo = next(((tipo, valor) for tipo, valor in eventos[1:] if tipo == "end"), None)
    fin = segundo[1] if segundo else duracion
    total = max(0.0, fin - primer_valor)
    if total > 1.0:
        return round(total, 3), [
            f"silencio inicial de {total:.2f}s supera el límite de 1s"
        ]
    return round(total, 3), []


def es_subtitulo(texto: Any) -> bool:
    norm = normalizar(texto)
    return any(marcador in norm for marcador in MARCADORES_ZONA["top"])


def a_pix(valor: Any, eje: str) -> float | None:
    texto = str(valor or "").strip().casefold()
    coincide = re.fullmatch(r"(-?\d+(?:\.\d+)?)(px|%)?", texto)
    if not coincide:
        return None
    numero = float(coincide.group(1))
    if coincide.group(2) == "%":
        return numero * (ANCHO if eje == "x" else ALTO) / 100
    return numero


def declaraciones(estilo: Any) -> dict[str, str]:
    resultado: dict[str, str] = {}
    for parte in str(estilo or "").split(";"):
        if ":" not in parte:
            continue
        clave, valor = parte.split(":", 1)
        resultado[clave.strip().casefold()] = valor.strip()
    return resultado


def zona_de_texto(texto: Any) -> str | None:
    norm = normalizar(texto)
    for zona in ("top", "main"):
        if any(marcador in norm for marcador in MARCADORES_ZONA[zona]):
            return zona
    return None


def atributos_de(atributos_crudos: Any) -> dict[str, str]:
    resultado: dict[str, str] = {}
    crudos = str(atributos_crudos or "")
    for coincidencia in RE_ATRIBUTO.finditer(crudos):
        coincidencia_clave = coincidencia.group(1).casefold()
        resultado[coincidencia_clave] = coincidencia.group(3)
    for nombre in ("data-layout-ignore", "data-caption", "data-media-vault", "muted", "playsinline", "autoplay"):
        if re.search(rf"\b{re.escape(nombre)}\b", crudos, re.IGNORECASE):
            resultado.setdefault(nombre, "")
    return resultado


def a_valor(valor: Any, padre: dict[str, float], eje: str) -> float | None:
    texto = str(valor or "").strip().casefold()
    coincide = re.fullmatch(r"(-?\d+(?:\.\d+)?)(px|%)?", texto)
    if not coincide:
        return None
    numero = float(coincide.group(1))
    if coincide.group(2) == "%":
        return numero * (float(padre["w"]) if eje == "x" else float(padre["h"])) / 100
    return numero


def geometria(estilo: dict[str, str], padre: dict[str, float]) -> dict[str, float]:
    ancho = a_valor(estilo.get("width", ""), padre, "x")
    alto = a_valor(estilo.get("height", ""), padre, "y")
    w = float(ancho) if ancho is not None else float(padre["w"])
    h = float(alto) if alto is not None else float(padre["h"])
    izquierda = a_valor(estilo.get("left", ""), padre, "x")
    derecha = a_valor(estilo.get("right", ""), padre, "x")
    arriba = a_valor(estilo.get("top", ""), padre, "y")
    abajo = a_valor(estilo.get("bottom", ""), padre, "y")
    if izquierda is not None:
        x = float(padre["x"]) + float(izquierda)
    elif derecha is not None:
        x = float(padre["x"]) + float(padre["w"]) - w - float(derecha)
    else:
        x = float(padre["x"])
    if arriba is not None:
        y = float(padre["y"]) + float(arriba)
    elif abajo is not None:
        y = float(padre["y"]) + float(padre["h"]) - h - float(abajo)
    else:
        y = float(padre["y"])
    return {"x": x, "y": y, "w": w, "h": h}


def reglas_por_selector(texto: str) -> dict[str, dict[str, str]]:
    reglas: dict[str, dict[str, str]] = {}
    for selector, cuerpo in re.findall(r"([^{}]+)\{([^{}]*)\}", texto):
        declaracion = declaraciones(cuerpo)
        if not declaracion:
            continue
        for parte in selector.split(","):
            nombre = parte.strip()
            if re.fullmatch(r"#[\w-]+", nombre) or re.fullmatch(r"\.[\w-]+", nombre):
                reglas.setdefault(nombre, {}).update(declaracion)
    return reglas


def elementos_html(texto: str) -> list[dict[str, Any]]:
    elementos: list[dict[str, Any]] = []
    reglas = reglas_por_selector(texto)
    pila: list[dict[str, Any]] = [
        {"etiqueta": "root", "geom": {"x": 0.0, "y": 0.0, "w": float(ANCHO), "h": float(ALTO)}, "ignorado": False}
    ]
    for coincidencia in RE_ETIQUETA.finditer(texto):
        cierre, etiqueta, crudo = coincidencia.groups()
        nombre = etiqueta.casefold()
        if cierre:
            for indice in range(len(pila) - 1, 0, -1):
                if pila[indice]["etiqueta"] == nombre:
                    del pila[indice:]
                    break
            continue
        attrs = atributos_de(crudo)
        estilo: dict[str, str] = {}
        identificador = attrs.get("id", "")
        if identificador:
            estilo.update(reglas.get(f"#{identificador}", {}))
        for clase in attrs.get("class", "").split():
            estilo.update(reglas.get(f".{clase}", {}))
        estilo.update(declaraciones(attrs.get("style", "")))
        geo = geometria(estilo, pila[-1]["geom"])
        ignorado = "data-layout-ignore" in attrs or bool(pila[-1].get("ignorado"))
        texto_directo = ""
        if nombre not in {"style", "script"} and nombre not in VOID_TAGS:
            contenido = contenido_de_etiqueta(texto, coincidencia.end(), nombre)
            texto_directo = limpiar(unescape(re.sub(r"<[^>]+>", " ", contenido.split("<", 1)[0])))
        elemento = {
            "etiqueta": nombre,
            "attrs": attrs,
            "estilo": estilo,
            "geom": geo,
            "id": identificador,
            "clase": attrs.get("class", ""),
            "texto": texto_directo,
            "ignorado": ignorado,
        }
        elementos.append(elemento)
        autoclose = crudo.rstrip().endswith("/")
        if nombre in VOID_TAGS or autoclose or nombre in {"style", "script"}:
            continue
        pila.append({"etiqueta": nombre, "geom": geo, "ignorado": ignorado})
    return elementos


def zona_del_elemento(elemento: dict[str, Any]) -> str | None:
    declarada = str(elemento["attrs"].get("data-zone", "")).casefold()
    if declarada:
        if declarada in ("caption", "subtitulo", "subtítulo", "subtitle", "top", "superior"):
            return "top"
        if declarada in ("main", "central", "title", "hero", "cta"):
            return "main"
        if declarada in ("hud", "telemetria", "telemetry", "dronehud"):
            return "top"
    if "data-caption" in elemento["attrs"]:
        return "top"
    return zona_de_texto(f"{elemento['id']} {elemento['clase']}")


def revisar_elementos(
    elementos: list[dict[str, Any]], origen: str, problemas: list[str]
) -> int:
    revisiones = 0
    for elemento in elementos:
        geo = elemento["geom"]
        nombre = elemento["id"] or elemento["clase"] or elemento["etiqueta"]
        posicionado = elemento["estilo"].get("position") in {"absolute", "fixed"}
        marker = any(clave in elemento["attrs"] for clave in ("data-zone", "data-caption")) or "clip" in elemento["clase"].split()
        contenedor = elemento["etiqueta"] in {"audio", "video", "source"} or elemento["id"] == "root"
        if not elemento.get("ignorado") and not contenedor and (posicionado or marker) and geo["y"] + geo["h"] > LIMITE_INFERIOR_VACIO:
            problemas.append(f"{origen}: «{nombre}» invade zona inferior libre desde y={LIMITE_INFERIOR_VACIO}px")
        zona = zona_del_elemento(elemento)
        if not zona:
            continue
        if "data-composition-src" in elemento["attrs"]:
            continue
        if elemento.get("ignorado") and "data-zone" not in elemento["attrs"]:
            continue
        limites = ZONAS[zona]
        revisiones += 1
        if geo["x"] < limites["left"] - 1 or geo["x"] + geo["w"] > limites["right"] + 1:
            problemas.append(f"{origen}: «{nombre}» de zona {zona} usa x={geo['x']:.0f}..{geo['x'] + geo['w']:.0f}, esperado {limites['left']}..{limites['right']}")
        if geo["y"] < limites["top"] - 1 or geo["y"] + geo["h"] > limites["bottom"] + 1:
            problemas.append(f"{origen}: «{nombre}» de zona {zona} usa y={geo['y']:.0f}..{geo['y'] + geo['h']:.0f}, esperado {limites['top']}..{limites['bottom']}")
    return revisiones


def revisar_reglas_css(texto: str, origen: str, problemas: list[str]) -> int:
    revisiones = 0
    for selector, cuerpo in re.findall(r"([^{}]+)\{([^{}]*)\}", texto):
        zona = zona_de_texto(selector)
        if not zona:
            continue
        limites = ZONAS[zona]
        reglas = declaraciones(cuerpo)
        for clave, eje in (("top", "y"), ("left", "x")):
            if clave not in reglas:
                continue
            valor = a_pix(reglas[clave], eje)
            if valor is None:
                continue
            revisiones += 1
            minimo = limites[clave]
            maximo = limites["bottom"] if clave == "top" else limites["right"]
            if not minimo <= valor <= maximo:
                problemas.append(
                    f"{origen}: regla {limpiar(selector)} usa {clave}={valor:.0f}px fuera de zona {zona}"
                )
            if clave == "top" and valor >= LIMITE_INFERIOR_VACIO:
                problemas.append(f"{origen}: regla {limpiar(selector)} usa top={valor:.0f}px en zona inferior vacía")
        for clave, eje, total in (("bottom", "y", ALTO), ("right", "x", ANCHO)):
            if clave not in reglas:
                continue
            valor = a_pix(reglas[clave], eje)
            if valor is None:
                continue
            revisiones += 1
            absolute = total - float(valor)
            minimo = total - limites["bottom"] if clave == "bottom" else total - limites["right"]
            maximo = total - limites["top"] if clave == "bottom" else total - limites["left"]
            if not minimo <= absolute <= maximo:
                problemas.append(
                    f"{origen}: regla {limpiar(selector)} usa {clave}={valor:.0f}px fuera de zona {zona}"
                )
    return revisiones


def contenido_de_etiqueta(texto: str, fin_apertura: int, etiqueta: str) -> str:
    profundidad = 1
    nombre = etiqueta.casefold()
    for coincidencia in RE_ETIQUETA.finditer(texto, fin_apertura):
        cierre, etiqueta_actual, crudo = coincidencia.groups()
        if etiqueta_actual.casefold() != nombre:
            continue
        if cierre:
            profundidad -= 1
            if profundidad == 0:
                return texto[fin_apertura:coincidencia.start()]
        elif not crudo.rstrip().endswith("/") and etiqueta_actual.casefold() not in VOID_TAGS:
            profundidad += 1
    return texto[fin_apertura : fin_apertura + 4000]


def revisar_bloques_subtitulo(texto: str, origen: str, problemas: list[str]) -> int:
    revisiones = 0
    for coincidencia in RE_ETIQUETA.finditer(texto):
        cierre, etiqueta, crudo = coincidencia.groups()
        if cierre:
            continue
        attrs = atributos_de(crudo)
        identificador = f"{attrs.get('id', '')} {attrs.get('class', '')}"
        if "data-caption" not in attrs and not es_subtitulo(identificador):
            continue
        if "clip" not in attrs.get("class", "") and "data-caption" not in attrs:
            continue
        contenido = contenido_de_etiqueta(texto, coincidencia.end(), etiqueta)
        if not contenido.strip():
            continue
        revisiones += 1
        nombre = attrs.get("id", "") or attrs.get("class", "") or etiqueta
        if re.search(r"</span><span", contenido, re.IGNORECASE):
            problemas.append(f"{origen}: «{nombre}» pega palabras sin espacio real")
        visible = limpiar(unescape(re.sub(r"<[^>]+>", " ", contenido)))
        palabras = [palabra for palabra in re.split(r"\s+", visible) if palabra]
        total_palabras = len(palabras)
        if total_palabras < 3 or total_palabras > 4:
            problemas.append(f"{origen}: «{nombre}» debe tener 3–4 palabras por bloque; tiene {total_palabras}")
        if total_palabras > 1 and visible.count(" ") < total_palabras - 1:
            problemas.append(f"{origen}: «{nombre}» tiene palabras pegadas; usa espacios reales entre tokens")
        if visible and " " not in visible and len(visible) > 12:
            problemas.append(f"{origen}: «{nombre}» parece una sola palabra pegada")
        if len(visible) < 4:
            problemas.append(f"{origen}: «{nombre}» no tiene texto de subtítulo legible")
    return revisiones


def revisar_estilo_subtitulo(texto: str, origen: str, problemas: list[str], presente: bool) -> None:
    if not presente:
        return
    normal = re.sub(r"\s+", " ", texto.casefold())
    # En la nueva plantilla, subtítulo superior es dinámico sin recuadro; si hay estilo antiguo, validar suavemente.
    if "caption-box" in normal or "--caption-bg" in normal:
        fondo = "rgba(0, 0, 0, 0.75)" in normal or "rgba(0,0,0,0.75)" in normal
        if not fondo:
            problemas.append(f"{origen}: recuadro de subtítulo sin fondo rgba(0, 0, 0, 0.75)")


def revisar_paleta(proyecto: Path) -> tuple[list[str], dict[str, Any]]:
    problemas: list[str] = []
    datos: dict[str, Any] | None = None
    origen = ""
    for relativo in ("config.json", "renders/metadata.json"):
        ruta = proyecto / relativo
        if not ruta.is_file():
            continue
        try:
            contenido = json.loads(ruta.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(contenido, dict):
            continue
        if isinstance(contenido.get("paleta"), (str, dict)):
            datos = contenido
            origen = relativo
            break
    if datos is None:
        return ["falta la paleta visual guardada en config.json o renders/metadata.json"], {"guardada": False}

    valor = datos.get("paleta")
    clave = str(datos.get("paleta_clave") or "").casefold()
    colores: dict[str, str] = {}
    if isinstance(valor, str):
        clave = clave or valor.casefold()
    elif isinstance(valor, dict):
        clave = clave or str(valor.get("clave") or "").casefold()
        colores = {str(k).casefold(): str(v).upper() for k, v in valor.items() if isinstance(v, str)}
    if not clave or clave not in PALETAS:
        coincidencias = [
            nombre
            for nombre, esperado in PALETAS.items()
            if all(colores.get(k) == v.upper() for k, v in esperado.items() if k in colores)
            and len(colores) >= 2
        ]
        if len(coincidencias) == 1:
            clave = coincidencias[0]
    if not clave or clave not in PALETAS:
        problemas.append(f"{origen}: paleta visual «{clave or valor}» no está entre las 4 paletas permitidas")
        return problemas, {"guardada": True, "origen": origen, "clave": clave, "valida": False}

    esperado = PALETAS[clave]
    for nombre, color in esperado.items():
        if nombre in colores and colores[nombre] != color.upper():
            problemas.append(f"{origen}: {nombre}={colores[nombre]} no coincide con paleta {clave} ({color})")
    return problemas, {
        "guardada": True,
        "origen": origen,
        "clave": clave,
        "colores": colores or esperado,
        "valida": not problemas,
    }


def revisar_estilo(proyecto: Path) -> tuple[list[str], dict[str, Any]]:
    problemas: list[str] = []
    ids: dict[str, str] = {}
    paletas_declared: dict[str, str] = {}
    duraciones: dict[str, float] = {}
    for relativo in ("config.json", "renders/metadata.json"):
        ruta = proyecto / relativo
        if not ruta.is_file():
            continue
        try:
            datos = json.loads(ruta.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(datos, dict):
            continue
        valor = datos.get("estilo_id") or datos.get("estilo")
        if isinstance(valor, dict):
            valor = valor.get("id")
        if valor:
            ids[relativo] = str(valor).strip()
        if datos.get("paleta_clave"):
            paletas_declared[relativo] = str(datos["paleta_clave"]).casefold()
        try:
            if datos.get("duracion_maxima_s") is not None:
                duraciones[relativo] = float(datos["duracion_maxima_s"])
        except (TypeError, ValueError):
            problemas.append(f"{relativo}: duracion_maxima_s no es numérico")

    if not ids:
        return problemas, {"declarado": False}

    valores_unicos = set(ids.values())
    if len(valores_unicos) > 1:
        problemas.append(f"estilo visual inconsistente entre archivos: {', '.join(sorted(valores_unicos))}")
    estilo_id = sorted(valores_unicos)[0]
    if estilo_id not in estilos_video.ESTILOS:
        problemas.append(f"estilo visual «{estilo_id}» no está en el catálogo de 10 estilos")
        return problemas, {"declarado": True, "id": estilo_id, "valida": False}

    estilo = estilos_video.obtener(estilo_id)
    for relativo, paleta in paletas_declared.items():
        if paleta != estilo["paleta"]:
            problemas.append(f"{relativo}: paleta {paleta} no corresponde al estilo {estilo_id} ({estilo['paleta']})")
    for relativo, duracion in duraciones.items():
        if duracion > estilos_video.DURACION_MAXIMA_S:
            problemas.append(f"{relativo}: duracion_maxima_s {duracion} supera el máximo de 60 s")

    index = proyecto / "index.html"
    if index.is_file():
        texto = index.read_text(encoding="utf-8", errors="replace")
        coincidencia = re.search(r'data-style="([^"]+)"', texto)
        if coincidencia and coincidencia.group(1) != estilo_id:
            problemas.append(f"index.html data-style={coincidencia.group(1)} no coincide con {estilo_id}")

    return problemas, {
        "declarado": True,
        "id": estilo_id,
        "referencia": estilo["referencia"],
        "nombre": estilo["nombre"],
        "paleta": estilo["paleta"],
        "valida": not problemas,
    }


def revisar_curva_edicion(proyecto: Path) -> list[str]:
    ruta = proyecto / "config.json"
    if not ruta.is_file():
        return []
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(datos, dict):
        return []

    def numero(valor: Any) -> float:
        try:
            return float(valor or 0)
        except (TypeError, ValueError):
            return 0.0

    problemas: list[str] = []
    curva = datos.get("curva_edicion")
    if isinstance(curva, dict):
        gancho = curva.get("gancho")
        desarrollo = curva.get("desarrollo")
        micro = curva.get("micro_estimulo")
        if isinstance(gancho, dict):
            if not 0.9 <= numero(gancho.get("corte_min_s")) <= 1.3:
                problemas.append("curva_edicion.gancho.corte_min_s debe estar entre 0.9 y 1.3")
            if not 0.9 <= numero(gancho.get("corte_max_s")) <= 1.3:
                problemas.append("curva_edicion.gancho.corte_max_s debe estar entre 0.9 y 1.3")
        if isinstance(desarrollo, dict):
            if not 2.0 <= numero(desarrollo.get("corte_min_s")) <= 2.5:
                problemas.append("curva_edicion.desarrollo.corte_min_s debe estar entre 2.0 y 2.5")
            if not 2.0 <= numero(desarrollo.get("corte_max_s")) <= 2.5:
                problemas.append("curva_edicion.desarrollo.corte_max_s debe estar entre 2.0 y 2.5")
        if isinstance(micro, dict):
            if abs(numero(micro.get("cada_s")) - 3.5) > 0.001:
                problemas.append("curva_edicion.micro_estimulo.cada_s debe ser 3.5")
            zoom = micro.get("zoom")
            if not isinstance(zoom, list) or len(zoom) != 2 or numero(zoom[0]) != 1.0 or numero(zoom[1]) != 1.1:
                problemas.append("curva_edicion.micro_estimulo.zoom debe ser [1.0, 1.1]")

    zonas = datos.get("zonas_visuales")
    if isinstance(zonas, dict):
        superior = zonas.get("superior")
        central = zonas.get("central")
        inferior = numero(zonas.get("inferior_vacia_desde"))
        if isinstance(superior, dict):
            if numero(superior.get("top")) != 200 or numero(superior.get("bottom")) != 340:
                problemas.append("zonas_visuales.superior debe ser 200..340")
        if isinstance(central, dict):
            if numero(central.get("top")) != 380 or numero(central.get("bottom")) != 1260:
                problemas.append("zonas_visuales.central debe ser 380..1260")
        if inferior and inferior != 1320:
            problemas.append("zonas_visuales.inferior_vacia_desde debe ser 1320")
    return problemas


def revisar_plantilla(proyecto: Path) -> list[str]:
    problemas: list[str] = []
    index = proyecto / "index.html"
    if not index.is_file():
        return ["falta index.html en el proyecto"]
    texto = index.read_text(encoding="utf-8", errors="replace")
    if "palette.js" not in texto:
        problemas.append("index.html no carga assets/scripts/palette.js")
    if "data-composition-variables" not in texto or "palette" not in texto:
        problemas.append("index.html no expone la variable automática palette/categoria")
    combinado = texto
    for ruta in proyecto.glob("compositions/**/*.html"):
        if ruta.is_file():
            combinado += "\n" + ruta.read_text(encoding="utf-8", errors="replace")
    for zona in ZONAS:
        if f'data-zone="{zona}"' not in combinado:
            problemas.append(f'falta marcador data-zone="{zona}" en la plantilla del proyecto')
    if "data-composition-src=\"compositions/cta.html\"" not in texto:
        problemas.append("index.html no monta compositions/cta.html para el cierre interactivo")
    cta = proyecto / "compositions" / "cta.html"
    if not cta.is_file():
        problemas.append("falta compositions/cta.html con el cierre interactivo")
    elif 'id="cta-question"' not in cta.read_text(encoding="utf-8", errors="replace"):
        problemas.append("cta.html no tiene la pregunta visual de cierre")
    problemas.extend(revisar_curva_edicion(proyecto))
    return problemas


def archivos_composicion(proyecto: Path) -> list[Path]:
    patrones = (
        "index.html",
        "*.css",
        "styles.css",
        "style.css",
        "compositions/*.html",
        "compositions/**/*.html",
        "assets/**/*.css",
    )
    rutas: set[Path] = set()
    for patron in patrones:
        rutas.update(ruta for ruta in proyecto.glob(patron) if ruta.is_file())
    return sorted(rutas)


def revisar_solapamientos(elementos: list[dict[str, Any]], origen: str, problemas: list[str]) -> None:
    cajas: list[tuple[str, str, dict[str, float], str]] = []
    for elemento in elementos:
        zona = zona_del_elemento(elemento)
        if zona not in ZONAS:
            continue
        if elemento.get("ignorado") or "data-composition-src" in elemento["attrs"]:
            continue
        nombre = elemento["id"] or elemento["clase"] or elemento["etiqueta"]
        cajas.append((zona, nombre, elemento["geom"], str(elemento.get("texto") or "")))
    for i, (zona_a, nombre_a, a, texto_a) in enumerate(cajas):
        for zona_b, nombre_b, b, texto_b in cajas[i + 1:]:
            if zona_a == zona_b and not (texto_a and texto_b):
                continue
            ancho = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"])
            alto = min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"])
            if ancho <= 1 or alto <= 1:
                continue
            area = ancho * alto
            menor = min(max(1.0, a["w"] * a["h"]), max(1.0, b["w"] * b["h"]))
            if area / menor < 0.25:
                continue
            problemas.append(f"{origen}: solapamiento entre zona {zona_a} «{nombre_a}» y zona {zona_b} «{nombre_b}»")


def extraer_frames(video: Path, duracion: float, proyecto: Path) -> tuple[list[Path], list[str]]:
    problemas: list[str] = []
    frames_dir = proyecto / "renders" / "qa_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    for viejo in frames_dir.glob("frame_*.png"):
        try:
            viejo.unlink()
        except OSError:
            pass
    ffmpeg = resolver_herramienta("ffmpeg")
    rutas: list[Path] = []
    for ratio in FRAMES_QA:
        segundo = max(0.0, min(duracion - 0.1, duracion * ratio))
        nombre = f"frame_{int(ratio * 100)}.png"
        destino = frames_dir / nombre
        cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{segundo:.3f}", "-i", str(video), "-frames:v", "1", "-update", "1", str(destino)]
        proceso = ejecutar(cmd, timeout=120)
        if proceso.returncode != 0 or not destino.is_file():
            problemas.append(f"ffmpeg no pudo extraer frame {int(ratio*100)}%: {limpiar(proceso.stderr)[:180]}")
            continue
        rutas.append(destino)
    return rutas, problemas


def revisar_frames(frames: list[Path]) -> list[str]:
    problemas: list[str] = []
    ffmpeg = resolver_herramienta("ffmpeg")

    def valor_signal(salida: str, clave: str) -> float | None:
        for linea in reversed(salida.splitlines()):
            if f"lavfi.signalstats.{clave}" not in linea:
                continue
            try:
                return float(linea.split("=")[-1].strip())
            except ValueError:
                return None
        return None

    for frame in frames:
        cmd_inferior = [
            ffmpeg, "-hide_banner", "-i", str(frame),
            "-vf", f"crop={ANCHO}:{ALTO - LIMITE_INFERIOR_VACIO}:0:{LIMITE_INFERIOR_VACIO},signalstats,metadata=mode=print:file=-",
            "-f", "null", "-",
        ]
        proceso = ejecutar(cmd_inferior, timeout=60)
        salida = (proceso.stderr or "") + "\n" + (proceso.stdout or "")
        ydif = valor_signal(salida, "YDIF")
        ymax = valor_signal(salida, "YMAX")
        if ydif is not None and ydif > 18:
            problemas.append(f"{frame.name}: actividad visual en zona inferior libre (YDIF={ydif:.1f})")
        if ymax is not None and ymax > 245 and ydif is not None and ydif > 10:
            problemas.append(f"{frame.name}: posible texto/gráfico en zona inferior libre (YMAX={ymax:.0f})")

        cmd_contenido = [
            ffmpeg, "-hide_banner", "-i", str(frame),
            "-vf", f"crop={ANCHO}:{ZONAS['main']['bottom'] - ZONAS['top']['top']}:0:{ZONAS['top']['top']},signalstats,metadata=mode=print:file=-",
            "-f", "null", "-",
        ]
        proceso = ejecutar(cmd_contenido, timeout=60)
        salida = (proceso.stderr or "") + "\n" + (proceso.stdout or "")
        ymin = valor_signal(salida, "YMIN")
        ymax = valor_signal(salida, "YMAX")
        if ymin is not None and ymax is not None and ymax - ymin < 45:
            problemas.append(f"{frame.name}: contraste bajo en zonas seguras (rango Y={ymax - ymin:.0f})")
    return problemas


def revisar_safe_zones(proyecto: Path) -> tuple[list[str], dict[str, Any]]:
    problemas: list[str] = []
    revisiones = 0
    notas: list[str] = []

    problemas.extend(revisar_plantilla(proyecto))
    problemas_paleta, detalle_paleta = revisar_paleta(proyecto)
    problemas.extend(problemas_paleta)

    for ruta in archivos_composicion(proyecto):
        try:
            texto = ruta.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        origen = str(ruta.relative_to(proyecto)).replace("\\", "/")
        elementos = elementos_html(texto)
        revisiones += revisar_elementos(elementos, origen, problemas)
        revisar_solapamientos(elementos, origen, problemas)
        revisiones += revisar_reglas_css(texto, origen, problemas)
        revisiones += revisar_bloques_subtitulo(texto, origen, problemas)
        revisar_estilo_subtitulo(texto, origen, problemas, any(zona_del_elemento(e) == "top" and "data-caption" in e["attrs"] for e in elementos))

    for ruta in proyecto.rglob("*.ass"):
        if any(parte in {"node_modules", ".hyperframes", ".git"} for parte in ruta.parts):
            continue
        try:
            texto = ruta.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        resx = re.search(r"PlayResX:\s*(\d+)", texto, re.IGNORECASE)
        resy = re.search(r"PlayResY:\s*(\d+)", texto, re.IGNORECASE)
        base_ancho = int(resx.group(1)) if resx else ANCHO
        base_alto = int(resy.group(1)) if resy else ALTO
        escala_x = ANCHO / base_ancho if base_ancho else 1
        escala_y = ALTO / base_alto if base_alto else 1
        for linea in texto.splitlines():
            if not linea.lower().startswith("dialogue:"):
                continue
            partes = linea.split(",", 9)
            if len(partes) < 10:
                continue
            texto_sub = re.sub(r"\{[^}]*\}", "", partes[9])
            lineas = max(1, len(re.split(r"\\N|\\n", texto_sub)))
            pos = RE_POSICION_ASS.search(partes[9])
            if not pos:
                continue
            revisiones += 1
            x = float(pos.group(1)) * escala_x
            y = float(pos.group(2)) * escala_y
            limites = ZONAS["top"]
            if not limites["left"] <= x <= limites["right"]:
                problemas.append(f"{ruta.name}: subtítulo ASS fuera del ancho de zona superior {x:.0f}px")
            if y > limites["bottom"] or y < limites["top"]:
                problemas.append(f"{ruta.name}: subtítulo ASS fuera de zona superior y={y:.0f}px")
            if y + 40 * lineas > LIMITE_INFERIOR_VACIO:
                problemas.append(f"{ruta.name}: subtítulo ASS invade zona inferior libre")

    if revisiones == 0:
        notas.append("No se encontraron elementos posicionados; se validó la plantilla vertical-pro.")

    return problemas, {
        "revisiones": revisiones,
        "notas": notas,
        "zonas": {nombre: {"top": limits["top"], "bottom": limits["bottom"], "left": limits["left"], "right": limits["right"]} for nombre, limits in ZONAS.items()},
        "limite_inferior_vacio": LIMITE_INFERIOR_VACIO,
        "paleta": detalle_paleta,
    }


def validar_video(proyecto: Path, video: Path | None = None) -> tuple[bool, str, dict[str, Any]]:
    proyecto = Path(proyecto).resolve()
    video_path = ruta_video(proyecto, video).resolve()
    if not video_path.is_file():
        raise FileNotFoundError(f"No existe el MP4 {video_path}")

    datos, problemas = probe_video(video_path)
    silencio, problemas_audio = analizar_silencio_inicial(video_path, float(datos.get("duracion") or 0))
    problemas.extend(problemas_audio)
    problemas_safe, detalle_safe = revisar_safe_zones(proyecto)
    problemas.extend(problemas_safe)
    problemas_estilo, detalle_estilo = revisar_estilo(proyecto)
    problemas.extend(problemas_estilo)

    frames: list[Path] = []
    problemas_frames: list[str] = []
    duracion = float(datos.get("duracion") or 0)
    if duracion > 0:
        frames, problemas_frames = extraer_frames(video_path, duracion, proyecto)
        problemas.extend(problemas_frames)
        problemas.extend(revisar_frames(frames))

    resultado = {
        "proyecto": str(proyecto),
        "video": str(video_path),
        "tecnico": datos,
        "silencio_inicial_s": silencio,
        "safe_zones": detalle_safe,
        "estilo": detalle_estilo,
        "frames_qa": [str(ruta) for ruta in frames],
        "problemas": problemas,
    }
    return not problemas, "; ".join(problemas) if problemas else "QA OK", resultado


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="QA técnico y de safe zones antes de agendar un video.")
    parser.add_argument("proyecto", help="Carpeta del proyecto")
    parser.add_argument("--video", help="Ruta MP4 concreta; por defecto se toma renders/metadata.json")
    args = parser.parse_args(argv)

    try:
        ok, detalle, resultado = validar_video(
            Path(args.proyecto), Path(args.video) if args.video else None
        )
    except Exception as error:
        print(json.dumps({"ok": False, "detalle": f"{type(error).__name__}: {error}"}, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps({"ok": ok, "detalle": detalle, **resultado}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
