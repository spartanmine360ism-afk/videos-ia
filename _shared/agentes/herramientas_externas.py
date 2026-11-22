from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parents[1] / "cache" / "github_tools"
SCRIPTS = Path(__file__).resolve().parents[1] / "templates" / "vertical-pro" / "assets" / "scripts"

REPOS = {
    "PHANTOMTONYT/motion-design-skills": {
        "licencia": "MIT",
        "uso": "cartoon 2D dibujado en código, typography kinetic, diagramas y personaje 3D tipo juguete",
        "archivos": ["hand-drawn-cartoon/SKILL.md", "3d-toy-character/SKILL.md", "kinetic-typography/SKILL.md", "data-story-charts/SKILL.md", "system-diagram-animation/SKILL.md"],
    },
    "krisuuu2/code-cartoon-skill": {
        "licencia": "MIT",
        "uso": "contrato de escenas puras en función del tiempo, voz antes que imagen y QA sin ver el video",
        "archivos": ["SKILL.md"],
    },
    "obeskay/lottie-animator-skill": {
        "licencia": "MIT",
        "uso": "convertir SVG a Lottie, lint de animación y principios de movimiento",
        "archivos": ["skills/lottie-animator/SKILL.md", "scripts/svg2lottie.py", "scripts/lottie_lint.py", "scripts/motion.py", "scripts/recolor.py"],
    },
    "cpppppp7/video2threejs": {
        "licencia": "MIT",
        "uso": "convertir referencias de video a escenas Three.js con cámara y FFmpeg locales",
        "archivos": ["SKILL.md", "forge/solve_camera.py"],
    },
    "cathrynlavery/diagram-design": {
        "licencia": "MIT",
        "uso": "HUD, diagramas técnicos, animación de diagramas y presupuesto de layout",
        "archivos": ["skills/diagram-design/SKILL.md", "skills/diagram-design/references/animation.md", "skills/diagram-design/references/style-guide.md"],
    },
    "SyedMuhammedAbbas/motion-studio": {
        "licencia": "MIT",
        "uso": "seek por fotograma, leyes de movimiento, ritmo con beats y checklist de revisión",
        "archivos": ["recipes/video-motion-craft/SKILL.md", "recipes/video-motion-craft/references/motion-laws.md", "recipes/video-motion-craft/references/beat-sync.md", "recipes/video-motion-craft/references/review-checklist.md"],
    },
}

BIBLIOTECAS = [
    {"nombre": "three", "version": "0.187.0", "licencia": "MIT", "archivos": ["three.module.js", "three.core.js"], "uso": "3D desde código sin modelos externos"},
    {"nombre": "d3", "version": "7.9.2", "licencia": "ISC", "archivos": ["d3.min.js"], "uso": "HUD y gráficos gobernados por datos"},
    {"nombre": "flubber", "version": "0.4.2", "licencia": "MIT", "archivos": ["flubber.min.js"], "uso": "morphing de paths SVG sin plugins de pago"},
    {"nombre": "lottie-web", "version": "local existente", "licencia": "MIT", "archivos": ["lottie.min.js"], "uso": "animación vectorial con seek exacto por frame"},
]

RECETAS = {
    "cartoon_2d": [
        "Dibuja el personaje como SVG con partes separadas: cuerpo, ojos, boca y extremidades.",
        "Haz que la tinta hierva con tres filtros de desplazamiento intercambiados cada dos fotogramas.",
        "Anticipación, movimiento, squash y settle en cada acción; parte 2–4 fotogramas las extremidades.",
        "Nunca uses Math.random ni reloj: todo debe derivar de la línea de tiempo.",
    ],
    "modelo_3d": [
        "Busca primero en la biblioteca de modelos 3D local; si no hay equivalente, construye con geometría Three.js.",
        "Usa materiales planos o con poco metal y una luz dominante; sin texturas remotas.",
        "El objeto se mueve con seek determinista, nunca con requestAnimationFrame libre.",
    ],
    "lottie_svg": [
        "Convierte SVG simples a Lottie con svg2lottie.py y valida con lottie_lint.py --strict.",
        "Toda animación debe tener al menos una propiedad animada: rotación, escala, posición u opacidad.",
        "Usa renderer svg para iconos pequeños y goToAndStop(frame, true) desde la línea de tiempo.",
    ],
    "hud_d3": [
        "Construye gráficos con D3 a partir de datos deterministas y actualízalos con seek(t).",
        "Usa Flubber para morphing de paths y conserva una sola fuente de verdad para los números en pantalla.",
        "El HUD permanece en la zona superior o central; el texto nunca baja de y=1320.",
    ],
    "render": [
        "El render sirve el proyecto por HTTP local para permitir módulos ES y fetch de archivos propios.",
        "Cada fotograma es una función pura de t: no existe estado acumulado entre capturas.",
        "Valida con duration<=60, OCR, cero solapes y ningún texto cortado antes de publicar.",
    ],
}


def _leer_manifiesto() -> dict[str, Any]:
    ruta = BASE / "manifiesto.json"
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return datos if isinstance(datos, dict) else {}


def resumen() -> dict[str, Any]:
    manifiesto = _leer_manifiesto()
    disponibles = []
    for nombre, datos in REPOS.items():
        destino = BASE / nombre.replace("/", "__")
        archivos = list(datos["archivos"])
        presente = all((destino / archivo).is_file() for archivo in archivos)
        disponibles.append(
            {
                "repo": nombre,
                "licencia": datos["licencia"],
                "uso": datos["uso"],
                "ruta": str(destino),
                "disponible": presente,
                "registrado": nombre in manifiesto,
            }
        )
    vendored = []
    for dato in BIBLIOTECAS:
        presente = all((SCRIPTS / archivo).is_file() for archivo in dato["archivos"])
        vendored.append({**dato, "disponible": presente})
    return {
        "skills": disponibles,
        "bibliotecas": vendored,
        "recetas": RECETAS,
        "manifiesto": str(BASE / "manifiesto.json"),
    }


def texto_para_prompt() -> str:
    datos = resumen()
    lineas = ["HERRAMIENTAS EXTERNAS CACHEADAS Y VALIDADAS (usar solo en local):"]
    for elemento in datos["bibliotecas"]:
        if elemento["disponible"]:
            lineas.append(f"{elemento['nombre']}@{elemento['version']} ({elemento['licencia']}): {elemento['uso']}.")
    for elemento in datos["skills"]:
        if elemento["disponible"]:
            lineas.append(f"{elemento['repo']} ({elemento['licencia']}): {elemento['uso']} -> {elemento['ruta']}.")
    for nombre, reglas in RECETAS.items():
        lineas.append(f"{nombre}: " + " | ".join(reglas))
    return "\n".join(lineas)
