from __future__ import annotations

import html
import re
import sys
import unicodedata
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import requests
from ddgs import DDGS

ROOT_DIR = Path(__file__).resolve().parents[2]
FACTORY_DIR = Path(__file__).resolve().parent
REPORT_PATH = FACTORY_DIR / "mejoras_semanales.md"
AGENTS_PATH = ROOT_DIR / "AGENTS.md"
MARCA_AGENTS = "## Mejoras Continuas de Calidad y Diseño"
HEADERS = {
    "User-Agent": "AuraDronesWeeklyUpgradeRadar/1.0 (local; no install)",
    "Accept": "application/vnd.github+json, application/json;q=0.9, */*;q=0.8",
    "Accept-Language": "es-419,es;q=0.9,en;q=0.8",
}
SECCIONES: list[dict[str, Any]] = [
    {
        "titulo": "1. Plantillas y efectos de video (FFmpeg / Remotion / diseño / retención)",
        "github": ["remotion video templates", "ffmpeg video effects", "short form video retention editing"],
        "huggingface": [],
        "pypi": ["imageio-ffmpeg", "moviepy", "opencv-python-headless"],
    },
    {
        "titulo": "2. Voz gratis e ilimitada y modelos abiertos de video",
        "github": ["edge-tts text to speech", "open source text to video generation"],
        "huggingface": ["text to video", "text to speech"],
        "pypi": ["edge-tts", "TTS", "faster-whisper", "diffusers"],
    },
    {
        "titulo": "3. Skills y flujos nuevos para OpenCode",
        "github": ["opencode agent skills", "opencode video automation workflow"],
        "huggingface": [],
        "pypi": [],
    },
    {
        "titulo": "4. Comunidades de creadores (ganchos, ritmo y retención)",
        "github": [],
        "huggingface": [],
        "pypi": [],
        "comunidades": [
            "site:reddit.com/r/drones short video editing hooks retention 2026",
            "site:reddit.com/r/fpv cinematic drone editing transitions 2026",
            "site:youtube.com shorts retention hooks first 3 seconds 2026",
            "site:tiktok.com creator vertical video editing trends 2026",
        ],
    },
]


def limpiar(texto: Any) -> str:
    return re.sub(r"\s+", " ", html.unescape(str(texto or ""))).strip()


def slug(texto: Any) -> str:
    valor = unicodedata.normalize("NFKD", str(texto or ""))
    valor = "".join(caracter for caracter in valor if not unicodedata.combining(caracter))
    return re.sub(r"[^a-z0-9]+", "-", valor.casefold()).strip("-") or "recurso"


def md(texto: Any) -> str:
    return limpiar(texto).replace("|", "\\|").replace("\n", " ")


def obtener_json(url: str, params: dict[str, Any] | None = None) -> Any:
    respuesta = requests.get(url, params=params, headers=HEADERS, timeout=30)
    respuesta.raise_for_status()
    return respuesta.json()


def github_items(query: str) -> list[dict[str, Any]]:
    datos = obtener_json(
        "https://api.github.com/search/repositories",
        {"q": query, "sort": "updated", "order": "desc", "per_page": 4},
    )
    resultados: list[dict[str, Any]] = []
    for repo in datos.get("items", [])[:4]:
        url = limpiar(repo.get("html_url"))
        nombre = limpiar(repo.get("full_name"))
        if not url or not nombre:
            continue
        resultados.append(
            {
                "fuente": "GitHub",
                "nombre": nombre,
                "url": url,
                "descripcion": limpiar(repo.get("description")) or "Repositorio reciente sin descripción.",
                "detalle": f"★ {int(repo.get('stargazers_count') or 0)} · actualizado {limpiar(repo.get('pushed_at'))[:10]}",
                "comando": f'git clone --depth 1 "{url}" "_radar\\{slug(nombre)}"',
            }
        )
    return resultados


def huggingface_items(query: str) -> list[dict[str, Any]]:
    datos = obtener_json(
        "https://huggingface.co/api/models",
        {"search": query, "sort": "downloads", "direction": -1, "limit": 4},
    )
    resultados: list[dict[str, Any]] = []
    for modelo in datos[:4] if isinstance(datos, list) else []:
        identificador = limpiar(modelo.get("id"))
        if not identificador:
            continue
        url = f"https://huggingface.co/{identificador}"
        resultados.append(
            {
                "fuente": "Hugging Face",
                "nombre": identificador,
                "url": url,
                "descripcion": limpiar(modelo.get("pipeline_tag")) or "Modelo abierto relacionado con video/audio.",
                "detalle": f"descargas {int(modelo.get('downloads') or 0)} · {limpiar(modelo.get('lastModified'))[:10]}",
                "comando": f'git clone --depth 1 "{url}" "_radar\\{slug(identificador)}"',
            }
        )
    return resultados


def pypi_items(nombre: str) -> list[dict[str, Any]]:
    datos = obtener_json(f"https://pypi.org/pypi/{urllib.parse.quote(nombre, safe='')}/json")
    info = datos.get("info") or {}
    version = limpiar(info.get("version"))
    if not version:
        return []
    publicaciones = datos.get("releases", {}).get(version, [])
    fechas = [limpiar(item.get("upload_time_iso_8601")) for item in publicaciones if item.get("upload_time_iso_8601")]
    fecha = max(fechas)[:10] if fechas else "desconocida"
    url = limpiar(info.get("project_url")) or f"https://pypi.org/project/{nombre}/"
    return [
        {
            "fuente": "PyPI",
            "nombre": f"{limpiar(info.get('name')) or nombre}=={version}",
            "url": url,
            "descripcion": limpiar(info.get("summary")) or "Paquete publicado en PyPI.",
            "detalle": f"Última versión {version} · publicada {fecha}",
            "comando": (
                f'python -m pip install --index-url https://pypi.org/simple '
                f'{limpiar(info.get("name")) or nombre}=={version}'
            ),
        }
    ]


def comunidades_items(query: str) -> list[dict[str, Any]]:
    resultados = DDGS().text(query, max_results=4)
    hallazgos: list[dict[str, Any]] = []
    for item in resultados or []:
        url = limpiar(item.get("href") or item.get("url"))
        if not url.startswith(("http://", "https://")):
            continue
        nombre = limpiar(item.get("title")) or url
        descripcion = limpiar(item.get("body") or item.get("description")) or "Señal editorial de la comunidad."
        hallazgos.append(
            {
                "fuente": "Comunidades",
                "nombre": nombre,
                "url": url,
                "descripcion": descripcion,
                "detalle": limpiar(query),
                "comando": "No instalar; convertir en regla editorial y validar antes de aplicarla.",
            }
        )
    return hallazgos


def recolectar(seccion: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    hallazgos: list[dict[str, Any]] = []
    errores: list[str] = []

    for query in seccion.get("github", []):
        try:
            hallazgos.extend(github_items(query))
        except Exception as error:
            errores.append(f"GitHub · {query}: {type(error).__name__}: {error}")

    for query in seccion.get("huggingface", []):
        try:
            hallazgos.extend(huggingface_items(query))
        except Exception as error:
            errores.append(f"Hugging Face · {query}: {type(error).__name__}: {error}")

    for nombre in seccion.get("pypi", []):
        try:
            hallazgos.extend(pypi_items(nombre))
        except Exception as error:
            errores.append(f"PyPI · {nombre}: {type(error).__name__}: {error}")

    for query in seccion.get("comunidades", []):
        try:
            hallazgos.extend(comunidades_items(query))
        except Exception as error:
            errores.append(f"Comunidades · {query}: {type(error).__name__}: {error}")

    return hallazgos, errores


def banner(hallazgos: Iterable[dict[str, Any]], titulo: str) -> list[str]:
    lineas = [f"### {titulo}", ""]
    items = list(hallazgos)
    if not items:
        lineas.extend(["Sin hallazgos en esta consulta.", ""])
        return lineas
    for item in items:
        lineas.extend(
            [
                f"- **{md(item['nombre'])}** · {md(item['fuente'])}",
                f"  - Enlace oficial: {item['url']}",
                f"  - Por qué importa: {md(item['descripcion'])}",
                f"  - Señal: {md(item['detalle'])}",
                f"  - Comando propuesto (NO ejecutado): `{item['comando']}`",
                "",
            ]
        )
    return lineas


def seleccionar_senales(
    hallazgos: list[dict[str, Any]], terminos: tuple[str, ...], limite: int = 3
) -> list[dict[str, Any]]:
    seleccionados: list[dict[str, Any]] = []
    vistos: set[str] = set()
    for hallazgo in hallazgos:
        url = limpiar(hallazgo.get("url"))
        if url and url in vistos:
            continue
        texto = " ".join(
            limpiar(hallazgo.get(clave))
            for clave in ("nombre", "descripcion", "detalle", "fuente")
        ).casefold()
        if any(termino.casefold() in texto for termino in terminos):
            seleccionados.append(hallazgo)
            if url:
                vistos.add(url)
            if len(seleccionados) >= limite:
                break
    if seleccionados:
        return seleccionados
    return hallazgos[:limite]


def bloque_agents(hallazgos: list[dict[str, Any]]) -> str:
    ahora = datetime.now(timezone.utc)
    lineas = [
        MARCA_AGENTS,
        "",
        f"Actualizado automáticamente el {ahora.date().isoformat()} por `weekly_upgrade_radar.py`. "
        "Solo convierte señales públicas en reglas editoriales; no instala repositorios ni paquetes.",
        "",
        "#### Ritmo visual",
        "- Cambia de plano, ángulo, zoom o elemento HUD cada 2–3 segundos para sostener la retención.",
        "- Usa GSAP con eases con nombre (`expo.out`, `power4.out`, `back.out(1.3)`) y stagger breve; "
        "prohíbete `ease:\"none\"` y `ease:\"linear\"`.",
        "- Mantén la plantilla LOOK fija, un solo acento, safe zones y captions karaoke sincronizadas.",
        "",
        "#### Ganchos",
        "- El primer fotograma y la primera línea deben exponer tensión, beneficio o dato concreto antes de 1.5 s.",
        "- Prohíbete arranques genéricos; nombra el modelo, el problema o el resultado verificable.",
        "- Cada red estrena gancho, copy y hashtags propios; reutilizar copy entre plataformas es un error de calidad.",
        "",
        "#### Estilo",
        "- Tipografía de impacto con alto contraste, jerarquía clara y microtexto en mayúsculas espaciadas.",
        "- SFX locales en sus tiempos exactos y voz edge-tts normalizada; sin audio remoto ni recursos externos en render.",
        "- Cero `filter:blur`, `backdrop-filter`, CDN o `fetch`; cualquier enfoque nuevo se adopta solo tras validación manual.",
        "",
    ]

    grupos = (
        ("ritmo visual y edición", ("corte", "edit", "retention", "transition", "ritmo", "plano", "zoom")),
        ("ganchos y retención", ("hook", "gancho", "retention", "first", "tiktok", "shorts", "reddit")),
        ("estilo y diseño", ("design", "diseño", "template", "remotion", "font", "color", "caption")),
    )
    for titulo, terminos in grupos:
        seleccionados = seleccionar_senales(hallazgos, terminos)
        if not seleccionados:
            continue
        lineas.extend([f"#### Señales de la semana · {titulo}", ""])
        for hallazgo in seleccionados:
            lineas.append(
                f"- {md(hallazgo.get('nombre'))}: {md(hallazgo.get('descripcion'))[:260]} "
                f"({limpiar(hallazgo.get('url'))})"
            )
        lineas.append("")

    return "\n".join(lineas).rstrip() + "\n"


def actualizar_agents(hallazgos: list[dict[str, Any]]) -> int:
    bloque = bloque_agents(hallazgos)
    contenido = AGENTS_PATH.read_text(encoding="utf-8", errors="replace")
    if MARCA_AGENTS in contenido:
        inicio = contenido.index(MARCA_AGENTS)
        finales = [
            posicion
            for posicion in (
                contenido.find("\n---", inicio),
                contenido.find("\n## ", inicio + len(MARCA_AGENTS)),
            )
            if posicion >= 0
        ]
        fin = min(finales) if finales else len(contenido)
        actualizado = contenido[:inicio] + bloque + contenido[fin:]
    else:
        actualizado = contenido.rstrip() + "\n\n---\n\n" + bloque
    temporal = AGENTS_PATH.with_name(AGENTS_PATH.name + ".tmp")
    temporal.write_text(actualizado, encoding="utf-8")
    temporal.replace(AGENTS_PATH)
    return bloque.count("\n- ") + 1


def generar_reporte() -> tuple[str, int, int, list[dict[str, Any]]]:
    ahora = datetime.now(timezone.utc)
    lineas = [
        f"# Radar semanal de mejoras — {ahora.date().isoformat()}",
        "",
        "Generado por `weekly_upgrade_radar.py`. **No se instaló ni ejecutó ninguna mejora.**",
        "Revisa licencia, fecha, compatibilidad y seguridad antes de copiar cualquier comando.",
        "Los paquetes nuevos requieren aprobación explícita, actualización de `_shared/requirements.txt` y `python -m pip check`.",
        "",
    ]
    total = 0
    todos_errores: list[str] = []
    todos_hallazgos: list[dict[str, Any]] = []

    for seccion in SECCIONES:
        lineas.extend([f"## {md(seccion['titulo'])}", ""])
        hallazgos, errores = recolectar(seccion)
        total += len(hallazgos)
        todos_hallazgos.extend(hallazgos)
        todos_errores.extend(errores)
        lineas.extend(banner([h for h in hallazgos if h["fuente"] == "GitHub"], "GitHub"))
        lineas.extend(banner([h for h in hallazgos if h["fuente"] == "Hugging Face"], "Hugging Face"))
        lineas.extend(banner([h for h in hallazgos if h["fuente"] == "PyPI"], "PyPI"))
        lineas.extend(banner([h for h in hallazgos if h["fuente"] == "Comunidades"], "Comunidades"))

    lineas.extend(["## Fuentes con error", ""])
    if todos_errores:
        lineas.extend([f"- {md(error)}" for error in todos_errores])
    else:
        lineas.append("- Ninguna.")
    lineas.append("")
    return "\n".join(lineas), total, len(todos_errores), todos_hallazgos


def notificar_reporte_dominical() -> None:
    from zoneinfo import ZoneInfo

    if datetime.now(ZoneInfo("America/Mexico_City")).weekday() != 6:
        return
    try:
        import notificador_telegram

        aviso = notificador_telegram.enviar_reporte_semanal()
        print(
            f"Telegram semanal: {aviso['estado']} fecha={aviso['fecha']} "
            f"caracteres={aviso['caracteres']}"
        )
    except Exception as error:
        print(
            f"[AVISO] Telegram semanal no enviado: {type(error).__name__}: {error}",
            file=sys.stderr,
        )


def main() -> int:
    texto, total, errores, hallazgos = generar_reporte()
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(texto, encoding="utf-8")
    reglas = actualizar_agents(hallazgos)
    print(f"Reporte escrito: {REPORT_PATH}")
    print(f"AGENTS actualizado: {AGENTS_PATH} | Reglas/señales: {reglas}")
    print(f"Hallazgos: {total} | Errores: {errores}")
    notificar_reporte_dominical()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
