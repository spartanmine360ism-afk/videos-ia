from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT_DIR = Path(__file__).resolve().parents[2]
FACTORY_DIR = Path(__file__).resolve().parent
HISTORIAL_PATH = FACTORY_DIR / "historial_temas.json"
HISTORIAL_IDEAS_PATH = FACTORY_DIR / "historial_ideas.json"
IDEAS_PATH = FACTORY_DIR / "ideas_pendientes.json"
PUBLISHER_DIR = ROOT_DIR / "_shared" / "publisher"
COLA_PATH = PUBLISHER_DIR / "schedule_queue.json"
ANALYTICS_PATH = FACTORY_DIR / "analytics_feedback.json"
UMBRAL_SIMILITUD = 0.90
UMBRAL_PALABRAS = 0.90
IGNORAR = {".git", "node_modules", "__pycache__", ".hyperframes", "_shared", ".agents", ".claude", ".venv", "venv"}
STOPWORDS = {
    "a", "al", "ante", "con", "contra", "del", "desde", "donde", "durante", "el", "en", "entre", "para", "por",
    "que", "sin", "sobre", "un", "una", "uno", "unos", "unas", "y", "o", "de", "la", "las", "los", "su", "sus",
    "como", "cuando", "más", "mas", "este", "esta", "estos", "estas", "eso", "esa", "ese", "porque", "solo",
    "the", "and", "for", "with", "from", "that", "this", "how", "what", "why", "new", "tu", "tus", "mi", "mis",
    "video", "videos", "drone", "drones", "aura", "auradrones", "consejo", "consejos", "tip", "tips", "guia",
    "noticia", "noticias", "reel", "reels", "short", "shorts", "tiktok", "instagram", "facebook", "youtube",
    "viral", "tendencia", "trending", "mira", "vive", "esto", "algo", "todo", "nada", "puede", "debe", "ser",
}
TECNICOS = {
    "dji", "avata", "avata2", "mini4pro", "mini3pro", "mavic", "air3", "air2s", "inspire", "osmo", "pocket3",
    "fpv", "freestyle", "cinewhoop", "cinematico", "cinematografico", "gimbal", "cardan", "estabilizacion",
    "sensor", "sensores", "obstaculo", "obstaculos", "obstacle", "evitacion", "avoidance", "lidar", "vision",
    "bateria", "baterias", "carga", "cargador", "vuelo", "volar", "volarse", "control", "controlador", "mando",
    "simulador", "simulator", "elrs", "o3", "o4", "transmision", "video", "camara", "camaras", "lente", "lentes",
    "apertura", "iso", "obturador", "shutter", "tracking", "seguimiento", "hypersmooth", "zoom", "gran angular",
    "configuracion", "configura", "ajuste", "ajustes", "checklist", "modo", "manual", "automatico", "profesional",
    "toma", "plano", "transicion", "movimiento", "panoramica", "orbita", "picado", "contrapicado", "edicion",
    "captions", "subtitulos", "audiovisual", "creador", "creadores", "concurso", "convocatoria", "reto",
    "challenge", "ugc", "colaboracion", "collab", "certificado", "licencia", "aereo", "aerea", "seguridad",
}
DISTINTIVOS = {
    "avata2", "mini4pro", "mini3pro", "air3", "air2s", "osmo", "pocket3", "cinewhoop", "elrs", "o3", "o4",
    "simulador", "simulator", "obstaculos", "evitacion", "avoidance", "lidar", "gimbal", "cardan", "checklist",
    "freestyle", "tracking", "seguimiento", "convocatoria", "concurso", "ugc", "colaboracion", "collab",
}
CLAVES_TEXTO = {
    "title", "titulo", "description", "descripcion", "hashtags", "gancho", "copy", "video", "name", "nombre",
    "proyecto", "tema", "resumen", "pregunta_detonadora", "cta", "pregunta",
}
BLOQUES_METADATA = ("youtube", "tiktok", "instagram", "facebook")


def limpiar(texto: Any) -> str:
    return re.sub(r"\s+", " ", str(texto or "")).strip()


def normalizar(texto: Any) -> str:
    valor = unicodedata.normalize("NFKD", str(texto or ""))
    valor = "".join(caracter for caracter in valor if not unicodedata.combining(caracter))
    return re.sub(r"\s+", " ", valor.casefold()).strip()


def tokens(texto: Any) -> list[str]:
    return [palabra for palabra in re.findall(r"[a-z0-9]{3,}", normalizar(texto)) if palabra not in STOPWORDS]


def palabras_clave(texto: Any) -> list[str]:
    brutos = tokens(texto)
    if not brutos:
        return []
    tecnicos = {palabra for palabra in brutos if palabra in TECNICOS}
    claves = set(tecnicos)
    for palabra, _ in Counter(brutos).most_common(14):
        if len(palabra) >= 4:
            claves.add(palabra)
    for actual, siguiente in zip(brutos, brutos[1:]):
        if actual in TECNICOS and siguiente in TECNICOS:
            claves.add(f"{actual} {siguiente}")
    return sorted(claves)


def texto_de_valor(valor: Any) -> str:
    if isinstance(valor, str):
        return limpiar(valor)
    if isinstance(valor, list):
        return " ".join(texto_de_valor(item) for item in valor if item is not None)
    return ""


def textos_de_datos(datos: Any) -> list[str]:
    textos: list[str] = []

    def recorrer(valor: Any) -> None:
        if isinstance(valor, dict):
            for clave, hijo in valor.items():
                if clave.casefold() in CLAVES_TEXTO:
                    texto = texto_de_valor(hijo)
                    if texto:
                        textos.append(texto)
                recorrer(hijo)
        elif isinstance(valor, list):
            for hijo in valor:
                recorrer(hijo)

    recorrer(datos)
    return textos


def titulo_de_datos(datos: Any, textos: list[str]) -> str:
    if isinstance(datos, dict):
        for bloque in ("youtube", "tiktok", "instagram", "facebook"):
            valor = datos.get(bloque)
            if isinstance(valor, dict):
                titulo = limpiar(valor.get("title") or valor.get("titulo"))
                if titulo:
                    return titulo
        for clave in ("video", "titulo", "title", "name", "nombre"):
            titulo = limpiar(datos.get(clave))
            if titulo:
                return titulo
    for texto in textos:
        primera = limpiar(texto.splitlines()[0] if texto.splitlines() else texto)
        if len(primera) >= 12:
            return primera[:140]
    return ""


def leer_json(ruta: Path) -> Any:
    try:
        return json.loads(ruta.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return None


def registrar(proyecto: str, archivo: str, textos: list[str], datos: Any = None) -> dict[str, Any]:
    contenido = "\n".join(texto for texto in textos if texto)
    normalizado = normalizar(contenido)
    return {
        "proyecto": proyecto,
        "archivo": archivo,
        "titulo": titulo_de_datos(datos, textos),
        "resumen": limpiar(contenido)[:1600],
        "keywords": palabras_clave(contenido),
        "indice": normalizado[:6000],
        "indexado_en": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }


_CACHE_INDEX: dict[str, Any] = {"ts": 0.0, "data": None}


def indexar(escribir: bool = True, ttl_segundos: int = 900, forzar: bool = False) -> dict[str, Any]:
    import time
    ahora = time.time()
    if not forzar and not escribir and _CACHE_INDEX["data"] is not None and (ahora - float(_CACHE_INDEX["ts"])) < ttl_segundos:
        return _CACHE_INDEX["data"]
    if not forzar and HISTORIAL_PATH.is_file():
        try:
            edad = ahora - HISTORIAL_PATH.stat().st_mtime
            if edad < ttl_segundos:
                data = leer_json(HISTORIAL_PATH)
                if isinstance(data, dict) and isinstance(data.get("registros"), list):
                    _CACHE_INDEX.update({"ts": ahora, "data": data})
                    return data
        except Exception:
            pass
    registros: list[dict[str, Any]] = []
    proyectos: list[str] = []

    for child in sorted(ROOT_DIR.iterdir(), key=lambda ruta: ruta.name):
        if not child.is_dir() or child.name in IGNORAR:
            continue
        proyectos.append(child.name)
        rutas: set[Path] = set()
        for relativo in ("script.md", "guion.md", "metadata.json", "renders/metadata.json", "meta.json"):
            candidata = child / relativo
            if candidata.is_file():
                rutas.add(candidata)
        for patron in ("**/script.md", "**/guion.md", "**/metadata.json", "**/meta.json"):
            rutas.update(ruta for ruta in child.rglob(patron) if ruta.is_file())
        for ruta in sorted(rutas, key=lambda valor: str(valor)):
            try:
                contenido = ruta.read_text(encoding="utf-8", errors="replace")[:24000]
            except OSError:
                continue
            datos = None
            textos: list[str] = []
            if ruta.suffix.casefold() == ".json":
                datos = json.loads(contenido) if contenido.strip().startswith(("{", "[")) else None
                if datos is not None:
                    textos.extend(textos_de_datos(datos))
            if not textos:
                textos.append(limpiar(contenido))
            registros.append(registrar(child.name, str(ruta.relative_to(ROOT_DIR)).replace("\\", "/"), textos, datos))

    if COLA_PATH.is_file():
        datos_cola = leer_json(COLA_PATH) or {}
        for tarea in datos_cola.get("tareas", []):
            if not isinstance(tarea, dict):
                continue
            textos = [limpiar(tarea.get("video")), limpiar(tarea.get("proyecto")), limpiar(tarea.get("titulo") or tarea.get("title"))]
            for clave in ("metadata", "config", "plataformas", "resultado", "youtube", "tiktok", "instagram", "facebook"):
                valor = tarea.get(clave)
                if isinstance(valor, (dict, list)):
                    textos.extend(textos_de_datos(valor))
                elif valor:
                    textos.append(limpiar(valor))
            # incluir títulos/descripciones/hashtags de metadata por plataforma ya publicados/agendados
            meta = tarea.get("metadata") if isinstance(tarea.get("metadata"), dict) else {}
            for plat in ("youtube", "tiktok", "instagram", "facebook"):
                bloque = meta.get(plat)
                if isinstance(bloque, dict):
                    textos.append(limpiar(bloque.get("title") or bloque.get("titulo")))
                    textos.append(limpiar(bloque.get("description") or bloque.get("descripcion")))
                    textos.append(texto_de_valor(bloque.get("hashtags")))
            registros.append(registrar("schedule_queue", "schedule_queue.json", textos, tarea))

    rutas_ideas = sorted(FACTORY_DIR.glob("ideas*.json")) + sorted(FACTORY_DIR.glob("historial_ideas.json"))
    vistas = set()
    for ruta in rutas_ideas:
        rp = str(ruta.resolve())
        if rp in vistas:
            continue
        vistas.add(rp)
        datos_factory = leer_json(ruta) or {}
        elementos = datos_factory.get("ideas", []) if isinstance(datos_factory, dict) else []
        if not isinstance(elementos, list):
            continue
        for elemento in elementos:
            if not isinstance(elemento, dict):
                continue
            claves = ("titulo", "gancho", "enfoque", "resumen", "categoria", "url", "fuente", "motivo", "accion", "proyecto", "video")
            textos = [limpiar(elemento.get(clave)) for clave in claves]
            registros.append(registrar("factory", str(ruta.relative_to(ROOT_DIR)).replace("\\", "/"), textos, elemento))

    # Analytics / videos ya subidos (evitar repetir lo publicado)
    for ruta_analytics in [ANALYTICS_PATH, FACTORY_DIR / "metricas_publicadas.json", FACTORY_DIR / "videos_publicados.json"]:
        if not ruta_analytics.is_file():
            continue
        datos_a = leer_json(ruta_analytics)
        if datos_a is None:
            continue
        textos_a = textos_de_datos(datos_a)
        if not textos_a and isinstance(datos_a, dict):
            for k in ("ganadores", "videos", "items", "rows"):
                v = datos_a.get(k)
                if isinstance(v, list):
                    for item in v:
                        if isinstance(item, dict):
                            registros.append(registrar("analytics", str(ruta_analytics.relative_to(ROOT_DIR)).replace("\\", "/"), textos_de_datos(item) or [limpiar(item.get("titulo") or item.get("title"))], item))
        if textos_a:
            registros.append(registrar("analytics", str(ruta_analytics.relative_to(ROOT_DIR)).replace("\\", "/"), textos_a, datos_a))

    datos_historial = {
        "generado_en": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "fuentes": ["script.md", "guion.md", "metadata.json", "renders/metadata.json", "meta.json", "schedule_queue.json"],
        "proyectos_indexados": proyectos,
        "total_registros": len(registros),
        "registros": registros,
    }
    if escribir:
        HISTORIAL_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporal = HISTORIAL_PATH.with_name(HISTORIAL_PATH.name + ".tmp")
        temporal.write_text(json.dumps(datos_historial, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporal.replace(HISTORIAL_PATH)
    _CACHE_INDEX.update({"ts": __import__("time").time(), "data": datos_historial})
    return datos_historial


def cargar_registros() -> list[dict[str, Any]]:
    data = indexar(escribir=False, ttl_segundos=900)
    registros = data.get("registros", []) if isinstance(data, dict) else []
    return registros if isinstance(registros, list) else []


def extraer_pregunta_detonadora(datos: Any) -> str:
    if isinstance(datos, dict):
        for clave in ("pregunta_detonadora", "pregunta_cta", "cta", "pregunta"):
            valor = limpiar(datos.get(clave))
            if "?" in valor:
                return valor
        for bloque in BLOQUES_METADATA:
            valor = datos.get(bloque)
            if isinstance(valor, dict):
                encontrada = extraer_pregunta_detonadora(valor)
                if encontrada:
                    return encontrada
        return ""

    texto = limpiar(datos)
    lineas = [limpiar(linea) for linea in texto.splitlines() if limpiar(linea)]
    for linea in reversed(lineas):
        if "?" in linea:
            return linea
    return ""


def preguntas_detonadoras_recientes(limite: int = 8, excluir: Any = "") -> list[str]:
    exclusion = normalizar(excluir)
    rutas = sorted(
        ROOT_DIR.glob("*/renders/metadata.json"),
        key=lambda ruta: ruta.stat().st_mtime,
        reverse=True,
    )
    resultados: list[str] = []
    for ruta in rutas:
        if exclusion and exclusion in normalizar(ruta.parents[1].name):
            continue
        pregunta = extraer_pregunta_detonadora(leer_json(ruta))
        if pregunta:
            resultados.append(pregunta)
        if len(resultados) >= limite:
            break
    return resultados


def cta_repetida(pregunta: Any, excluir: Any = "") -> tuple[bool, dict[str, Any]]:
    actual = normalizar(pregunta)
    if not actual:
        return True, {"motivo": "CTA vacío", "similitud": 1.0, "anterior": ""}
    for anterior in preguntas_detonadoras_recientes(excluir=excluir):
        previa = normalizar(anterior)
        if actual == previa:
            return True, {"motivo": "CTA idéntico", "similitud": 1.0, "anterior": anterior}
        similitud = SequenceMatcher(None, actual, previa).ratio()
        if similitud >= 0.9:
            return True, {"motivo": "CTA casi idéntico", "similitud": round(similitud, 3), "anterior": anterior}
    return False, {"motivo": "CTA inédito", "similitud": 0.0, "anterior": ""}


def detalle_tema_repetido(titulo: Any, resumen: Any = "") -> tuple[bool, dict[str, Any]]:
    texto = f"{limpiar(titulo)} {limpiar(resumen)}".strip()
    if len(normalizar(texto)) < 12:
        return True, {"motivo": "texto demasiado corto", "similitud": 1.0, "coincidencias": []}

    claves = set(palabras_clave(texto))
    tecnicas = {palabra for palabra in claves if palabra in TECNICOS or " " in palabra}
    norm_titulo = normalizar(titulo)
    norm_texto = normalizar(texto)[:1800]
    mejor = 0.0
    mejor_registro = ""

    for registro in cargar_registros():
        indice = limpiar(registro.get("indice"))
        if not indice:
            continue
        sim_titulo = SequenceMatcher(None, norm_titulo, normalizar(registro.get("titulo"))[:400]).ratio()
        sim_texto = SequenceMatcher(None, norm_texto, indice[:1800]).ratio()
        similitud = max(sim_titulo, sim_texto)
        mejor = max(mejor, similitud)
        if similitud >= mejor:
            mejor_registro = limpiar(registro.get("archivo")) or limpiar(registro.get("proyecto"))

        claves_previas = set(registro.get("keywords", []))
        tecnicas_previas = {palabra for palabra in claves_previas if palabra in TECNICOS or " " in palabra}
        tecnicas_comunes = tecnicas & tecnicas_previas
        solapamiento = len(claves & claves_previas) / max(1, min(len(claves), len(claves_previas)))

        if similitud >= UMBRAL_SIMILITUD:
            return True, {
                "motivo": "similitud textual",
                "similitud": round(similitud, 3),
                "coincidencias": sorted(claves & claves_previas),
                "registro": mejor_registro,
            }
        if len(tecnicas_comunes) >= 8 and similitud >= 0.85:
            return True, {
                "motivo": "mismo enfoque técnico",
                "similitud": round(similitud, 3),
                "coincidencias": sorted(tecnicas_comunes),
                "registro": mejor_registro,
            }
        if solapamiento >= UMBRAL_PALABRAS and similitud >= 0.90:
            return True, {
                "motivo": "palabras clave coincidentes",
                "similitud": round(similitud, 3),
                "coincidencias": sorted(claves & claves_previas),
                "registro": mejor_registro,
            }

    return False, {
        "motivo": "tema inédito",
        "similitud": round(mejor, 3),
        "coincidencias": [],
        "registro": mejor_registro,
    }


def es_tema_repetido(titulo: Any, resumen: Any = "") -> bool:
    return detalle_tema_repetido(titulo, resumen)[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Índice anti-repetición de temas de Aura Drones.")
    parser.add_argument("--indexar", action="store_true", help="Regenera historial_temas.json")
    parser.add_argument("--verificar", nargs=2, metavar=("TITULO", "RESUMEN"), help="Verifica si un tema está repetido")
    parser.add_argument("--verificar-cta", metavar="FRASE", help="Verifica si la frase de cierre ya se usó")
    args = parser.parse_args(argv)

    if args.verificar_cta:
        repetido, detalle = cta_repetida(args.verificar_cta)
        print(json.dumps({"repetido": repetido, **detalle}, ensure_ascii=False, indent=2))
        return 0

    if args.verificar:
        repetido, detalle = detalle_tema_repetido(args.verificar[0], args.verificar[1])
        print(json.dumps({"repetido": repetido, **detalle}, ensure_ascii=False, indent=2))
        return 0

    datos = indexar()
    print(f"Historial escrito: {HISTORIAL_PATH}")
    print(f"Proyectos: {len(datos['proyectos_indexados'])} | Registros: {datos['total_registros']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
