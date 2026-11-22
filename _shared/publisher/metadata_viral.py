from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Callable

import texto_utf8

PLATAFORMAS = ("youtube", "facebook", "instagram", "tiktok")
LIMITES_HASHTAGS = {
    "youtube": (4, 5),
    "tiktok": (6, 6),
    "instagram": (8, 10),
    "facebook": (4, 5),
}
CANTIDADES_OBJETIVO = {"youtube": 5, "tiktok": 6, "instagram": 9, "facebook": 5}
TAGS_GENERICOS = [
    "Drones",
    "FPV",
    "ConsejosDeVuelo",
    "CineAereo",
    "TomasVirales",
    "ConfiguracionDrones",
    "VueloSeguro",
    "EdicionVideo",
    "Tecnologia",
    "NovedadesTecnologicas",
    "Comparativas",
    "AuraDrones",
    "Shorts",
]
TAGS_POR_CATEGORIA = (
    (
        ("cine", "edicion", "toma", "visual", "storyteller"),
        ["Drones", "CineAereo", "TomasCinematograficas", "EdicionVideo"],
    ),
    (
        ("fpv", "dji", "tip", "config", "vuelo", "maniobra"),
        ["Drones", "FPV", "ConsejosDeVuelo", "ConfiguracionDrones", "VueloSeguro"],
    ),
    (
        ("tech", "gadget", "novedad", "tecnolog", "comparativa", "herramienta"),
        ["Drones", "Tecnologia", "NovedadesTecnologicas", "Comparativas", "Dispositivos"],
    ),
    (
        ("embudo", "comercial", "aura", "negocio"),
        ["Drones", "AuraDrones", "ConsejosDeVuelo", "Tecnologia"],
    ),
)
INGLES_PROHIBIDO = (
    "drone",
    "fyp",
    "tok",
    "life",
    "photo",
    "aviation",
    "racing",
    "simracing",
    "setup",
    "storytell",
    "creator",
    "visual",
    "tool",
    "hack",
    "config",
    "short",
)
REEMPLAZOS_TAGS = {
    "fyp": "TomasVirales",
    "drone": "Drones",
    "dronetok": "Drones",
    "dronelife": "Drones",
    "drone photography": "CineAereo",
    "dronephotography": "CineAereo",
    "aviationtech": "Tecnologia",
    "simracing": "FPV",
    "fypdrones": "TomasVirales",
    "configdrones": "ConfiguracionDrones",
    "dronetips": "ConsejosDeVuelo",
    "herramientasia": "HerramientasIA",
    "novedades tech": "NovedadesTecnologicas",
}
CTA_PALABRAS = {
    "youtube": ("guarda", "comenta", "suscríb"),
    "tiktok": ("guarda", "comenta", "cuént", "opina"),
    "instagram": ("guarda", "comparte"),
    "facebook": ("comenta", "cuént", "comparte", "opina"),
}
CTA_TEXTO = {
    "youtube": "Guarda este tip y comenta qué modelo usas.",
    "tiktok": "Guárdalo para tu próximo vuelo y comenta qué harías tú.",
    "instagram": "Guarda este reel y compártelo con tu crew antes de volar.",
    "facebook": "Cuéntame en los comentarios qué opinas o compártelo con alguien a quien le sirva.",
}
PRIVACIDAD_VALIDA = {"public", "private", "unlisted"}


def _normalizar(texto: Any) -> str:
    valor = unicodedata.normalize("NFKD", texto_utf8.limpiar_utf8(texto))
    valor = "".join(caracter for caracter in valor if not unicodedata.combining(caracter))
    return re.sub(r"\s+", " ", valor.casefold()).strip()


def _limpiar_linea(texto: Any) -> str:
    valor = texto_utf8.limpiar_utf8(texto)
    valor = re.sub(r"\s+", " ", valor).strip()
    valor = re.sub(r"([¿¡])\s+", r"\1", valor)
    valor = re.sub(r"\s+([?!.,;:])", r"\1", valor)
    valor = re.sub(r"([!?]){2,}", lambda coincidencia: coincidencia.group(1)[-1], valor)
    valor = re.sub(r"(\|){2,}", "|", valor)
    return valor.strip()


def _recortar(valor: str, maximo: int = 54) -> str:
    if len(valor) <= maximo:
        return valor
    candidato = valor[:maximo].rsplit(" ", 1)[0] or valor[:maximo]
    return candidato.rstrip(" |.,;:-")


def normalizar_pregunta(texto: Any) -> str:
    valor = _limpiar_linea(texto)
    valor = re.sub(r"[¿?¡!]+", "", valor).strip().strip(" .;:,-–—")
    return f"¿{valor}?" if valor else ""


def _clave(texto: Any) -> str:
    return re.sub(r"[¿?¡!.,;:…|]+", "", _normalizar(texto))


def _extraer_pregunta(datos: Any, profundidad: int = 0, clave_cta: bool = False) -> str:
    if isinstance(datos, dict):
        for clave in ("pregunta_detonadora", "pregunta_cta", "cta", "pregunta"):
            if clave in datos:
                encontrada = _extraer_pregunta(datos[clave], profundidad + 1, True)
                if encontrada:
                    return encontrada
        for plataforma in PLATAFORMAS:
            if plataforma in datos:
                encontrada = _extraer_pregunta(datos[plataforma], profundidad + 1, False)
                if encontrada:
                    return encontrada
        return ""
    if isinstance(datos, (list, tuple)):
        for item in datos:
            encontrada = _extraer_pregunta(item, profundidad + 1, clave_cta)
            if encontrada:
                return encontrada
        return ""
    if not isinstance(datos, str):
        return ""
    lineas = [_limpiar_linea(linea) for linea in datos.splitlines() if _limpiar_linea(linea)]
    for linea in reversed(lineas):
        if "?" in linea or "¿" in linea:
            return normalizar_pregunta(linea)
    if clave_cta and datos.strip():
        return normalizar_pregunta(datos)
    return ""


def _tema(contexto: dict[str, Any]) -> str:
    for clave in ("titulo", "tema", "gancho", "resumen", "nombre", "video"):
        valor = contexto.get(clave)
        if not valor:
            continue
        texto = str(valor).splitlines()[0] if isinstance(valor, str) else str(valor)
        texto = re.sub(r"\b20\d{6,14}\b", " ", texto)
        texto = re.sub(r"\d{4}-\d{2}-\d{2}[_-]\d{2}-\d{2}-\d{2}", " ", texto)
        texto = re.sub(r"[-_]+", " ", texto)
        texto = re.sub(r"\s+", " ", texto).strip(" -|·.,;:")
        if texto:
            return texto[:70]
    return "este truco"


def _generar_pregunta(contexto: dict[str, Any], es_repetido: Callable[[str], bool] | None = None) -> str:
    tema = _tema(contexto)
    candidatas = (
        f"¿Cuál de estos consejos probarías primero con {tema}?",
        f"¿Te atreverías a aplicar {tema} en tu próximo vuelo?",
        f"¿Qué opinas de {tema}: lo usarías o lo descartarías?",
    )
    for candidata in candidatas:
        if not es_repetido or not es_repetido(candidata):
            return candidata
    return candidatas[-1]


def _tags_contexto(contexto: dict[str, Any]) -> list[str]:
    texto = " ".join(
        str(contexto.get(clave) or "")
        for clave in ("categoria", "titulo", "tema", "resumen", "gancho")
    )
    categoria = _normalizar(texto)
    tags: list[str] = []
    for claves, lista in TAGS_POR_CATEGORIA:
        if any(clave in categoria for clave in claves):
            tags.extend(lista)
            break
    tags.extend(TAGS_GENERICOS)
    resultado: list[str] = []
    vistos: set[str] = set()
    for tag in tags:
        if tag.casefold() not in vistos:
            vistos.add(tag.casefold())
            resultado.append(tag)
    return resultado


def _tag_valido(tag: str) -> bool:
    base = tag.casefold()
    if base in {"shorts", "fpv", "auradrones", "ia"} or base.startswith("dji"):
        return True
    return not any(palabra in base for palabra in INGLES_PROHIBIDO)


def hashtags(valor: Any) -> list[str]:
    if isinstance(valor, str):
        items = valor.replace(",", " ").split()
    elif isinstance(valor, (list, tuple, set)):
        items = [str(item) for item in valor]
    elif valor is None:
        items = []
    else:
        items = [str(valor)]
    resultado: list[str] = []
    for item in items:
        tag = texto_utf8.limpiar_utf8(item).strip().lstrip("#").replace(" ", "")
        if tag and tag.casefold() not in {valor.casefold() for valor in resultado}:
            resultado.append(tag)
    return resultado


def _normalizar_tags(valor: Any, plataforma: str, contexto: dict[str, Any]) -> list[str]:
    minimo, maximo = LIMITES_HASHTAGS[plataforma]
    objetivo = CANTIDADES_OBJETIVO[plataforma]
    resultado: list[str] = []
    vistos: set[str] = set()

    def agregar(tag: str) -> None:
        candidato = REEMPLAZOS_TAGS.get(tag.casefold(), tag)
        candidato = re.sub(r"[^0-9A-Za-zÀ-ÿ]", "", texto_utf8.limpiar_utf8(candidato))
        if not candidato or not _tag_valido(candidato):
            return
        if plataforma != "youtube" and candidato.casefold() == "shorts":
            return
        if candidato.casefold() in vistos:
            return
        vistos.add(candidato.casefold())
        resultado.append(candidato)

    for tag in hashtags(valor):
        if plataforma != "youtube" and tag.casefold() == "shorts":
            continue
        agregar(tag)
    if plataforma == "youtube":
        resultado = [tag for tag in resultado if tag.casefold() != "shorts"]
        vistos.discard("shorts")
        agregar("Shorts")
        resultado.remove("Shorts")
        resultado.insert(0, "Shorts")
    for candidato in _tags_contexto(contexto):
        if len(resultado) >= objetivo:
            break
        agregar(candidato)
    for candidato in TAGS_GENERICOS:
        if len(resultado) >= max(minimo, objetivo):
            break
        agregar(candidato)
    return resultado[:maximo]


def _normalizar_descripcion(
    plataforma: str, descripcion: Any, pregunta: str, contexto: dict[str, Any]
) -> str:
    lineas = [re.sub(r"[ \t]+", " ", texto_utf8.limpiar_utf8(linea)).strip() for linea in str(descripcion or "").splitlines()]
    lineas = [_limpiar_linea(linea) for linea in lineas if _limpiar_linea(linea)]
    clave = _clave(pregunta)
    lineas = [linea for linea in lineas if _clave(linea) != clave]
    cuerpo = [re.sub(r"^[•\-–—]+", "", linea).strip() for linea in lineas]
    cuerpo = [linea for linea in cuerpo if linea]
    if not cuerpo:
        resumen = _limpiar_linea(contexto.get("resumen") or contexto.get("gancho") or _tema(contexto))
        cuerpo = [resumen]
    if plataforma == "tiktok" and len(cuerpo[0]) < 12:
        gancho = _limpiar_linea(contexto.get("gancho") or contexto.get("titulo") or _tema(contexto))
        cuerpo[0] = gancho if len(gancho) >= 12 else f"Esto pasa con {_tema(contexto)} y casi nadie lo nota."
    texto_cuerpo = " ".join(cuerpo).casefold()
    cta = "" if any(palabra in texto_cuerpo for palabra in CTA_PALABRAS[plataforma]) else CTA_TEXTO[plataforma]
    if plataforma == "instagram":
        gancho = cuerpo.pop(0) if cuerpo else _limpiar_linea(_tema(contexto))
        viñetas = cuerpo[:3]
        while len(viñetas) < 3:
            extra = _limpiar_linea(contexto.get("resumen") or _tema(contexto))
            if _clave(extra) in {_clave(item) for item in viñetas}:
                extra = f"Detalle {len(viñetas) + 1} de {_tema(contexto)}"
            viñetas.append(extra)
        partes = [gancho, "\n".join(f"• {_limpiar_linea(item).rstrip('.')}." for item in viñetas)]
        if len(cuerpo) > 3:
            partes.append(_limpiar_linea(" ".join(cuerpo[3:])))
    else:
        partes = list(cuerpo)
    if cta:
        partes.append(cta)
    separador = "\n\n" if plataforma == "instagram" else "\n"
    resultado = f"{separador.join(parte for parte in partes if parte)}\n{pregunta}"
    return resultado.strip()


def _normalizar_titulo(config: dict[str, Any], contexto: dict[str, Any]) -> None:
    titulo = config.get("title") or config.get("titulo") or _tema(contexto)
    titulo = _limpiar_linea(titulo)
    titulo = re.sub(r"\s*\|\s*", " | ", titulo)
    titulo = re.sub(r"(\|\s*){2,}", "| ", titulo).strip(" |")
    if not titulo:
        titulo = _tema(contexto)
    titulo = _recortar(titulo)
    if "shorts" not in titulo.casefold():
        sufijo = " | Shorts"
        if len(titulo) + len(sufijo) < 55:
            titulo = f"{titulo.rstrip(' |.,;:-')}{sufijo}"
        else:
            titulo = f"{_recortar(titulo, 54 - len(sufijo))}{sufijo}"
    config["title"] = _limpiar_linea(titulo)


def _limpiar_gancho(valor: Any, contexto: dict[str, Any]) -> str:
    texto = texto_utf8.limpiar_utf8(valor).replace('"', "").replace("“", "").replace("”", "")
    texto = _limpiar_linea(texto)
    if not texto:
        texto = _tema(contexto)
    return _recortar(texto)


def _normalizar_experimento(metadata: dict[str, Any], contexto: dict[str, Any]) -> None:
    experimento = metadata.get("experimento_ab")
    if not isinstance(experimento, dict):
        experimento = {}
    tema = _tema(contexto)
    gancho_a = _limpiar_gancho(experimento.get("gancho_a") or f"Error común: {tema}", contexto)
    gancho_b = _limpiar_gancho(experimento.get("gancho_b") or f"Resultado directo: {tema}", contexto)
    if _clave(gancho_a) == _clave(gancho_b):
        gancho_b = _limpiar_gancho(f"Resultado directo: {tema}", contexto)
    if _clave(gancho_a) == _clave(gancho_b):
        gancho_b = _limpiar_gancho(f"Truco de {tema} en 15 segundos", contexto)
    experimento["experimento"] = "gancho"
    experimento["gancho_a"] = gancho_a
    experimento["gancho_b"] = gancho_b
    experimento["asignacion"] = {"youtube": "A", "tiktok": "B"}
    metadata["experimento_ab"] = experimento


def _normalizar_bloque(
    plataforma: str, bloque: Any, pregunta: str, contexto: dict[str, Any]
) -> dict[str, Any]:
    config = dict(bloque) if isinstance(bloque, dict) else {}
    config["pregunta_detonadora"] = pregunta
    config["description"] = _normalizar_descripcion(
        plataforma, config.get("description"), pregunta, contexto
    )
    config["hashtags"] = _normalizar_tags(config.get("hashtags"), plataforma, contexto)
    if plataforma == "youtube":
        privacidad = str(config.get("privacidad") or "public").strip().lower()
        config["privacidad"] = privacidad if privacidad in PRIVACIDAD_VALIDA else "public"
        _normalizar_titulo(config, contexto)
    return config


def guardar_metadata(metadata: dict[str, Any], ruta: Path | str) -> None:
    destino = Path(ruta)
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_name(destino.name + ".tmp")
    temporal.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporal.replace(destino)


def normalizar_metadata(
    metadata: dict[str, Any],
    contexto: dict[str, Any] | None = None,
    ruta: Path | str | None = None,
    es_cta_repetido: Callable[[str], bool] | None = None,
) -> tuple[dict[str, Any], bool]:
    limpio = texto_utf8.limpiar_datos_utf8(metadata) if isinstance(metadata, dict) else {}
    if not isinstance(limpio, dict):
        limpio = {}
    antes = json.dumps(limpio, ensure_ascii=False, sort_keys=True)
    ctx: dict[str, Any] = dict(contexto) if isinstance(contexto, dict) else {}
    for clave in ("tema", "titulo", "categoria", "resumen", "gancho", "video", "serie"):
        if limpio.get(clave):
            ctx.setdefault(clave, limpio[clave])
    pregunta = normalizar_pregunta(_extraer_pregunta(limpio) or _extraer_pregunta(ctx))
    if not pregunta or (es_cta_repetido and es_cta_repetido(pregunta)):
        pregunta = normalizar_pregunta(_generar_pregunta(ctx, es_cta_repetido))
    limpio["pregunta_detonadora"] = pregunta
    for plataforma in PLATAFORMAS:
        limpio[plataforma] = _normalizar_bloque(
            plataforma, limpio.get(plataforma), pregunta, ctx
        )
    _normalizar_experimento(limpio, ctx)
    cambio = json.dumps(limpio, ensure_ascii=False, sort_keys=True) != antes
    if cambio and ruta is not None:
        guardar_metadata(limpio, ruta)
    return limpio, cambio


def normalizar_config(
    plataforma: str,
    config: dict[str, Any],
    metadata: dict[str, Any] | None = None,
    contexto: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], bool]:
    if plataforma not in LIMITES_HASHTAGS or not isinstance(config, dict):
        return config, False
    antes = json.dumps(config, ensure_ascii=False, sort_keys=True)
    ctx: dict[str, Any] = {}
    if isinstance(metadata, dict):
        ctx.update(metadata)
    if isinstance(contexto, dict):
        ctx.update(contexto)
    pregunta = normalizar_pregunta(_extraer_pregunta(config) or _extraer_pregunta(ctx))
    if not pregunta:
        pregunta = normalizar_pregunta(_generar_pregunta(ctx))
    normalizado = _normalizar_bloque(plataforma, config, pregunta, ctx)
    if plataforma == "youtube":
        _normalizar_titulo(normalizado, ctx)
    config.clear()
    config.update(normalizado)
    return config, json.dumps(config, ensure_ascii=False, sort_keys=True) != antes
