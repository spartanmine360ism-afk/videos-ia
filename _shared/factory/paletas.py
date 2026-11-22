from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PALETAS: dict[str, dict[str, Any]] = {
    "tips": {"nombre": "Tips técnicos DJI / Configuración", "clave": "tips", "accent": "#00E5FF", "accent_2": "#F4FBFF", "ground": "#0B111A", "surface": "#101A27", "ink": "#F4FBFF", "font_display": "Outfit"},
    "fpv": {"nombre": "Vuelo FPV / Acción / Velocidad", "clave": "fpv", "accent": "#FF6B00", "accent_2": "#FFD166", "ground": "#0D0D0F", "surface": "#171216", "ink": "#FFF7ED", "font_display": "Outfit"},
    "cine": {"nombre": "Tomas cinematográficas / Edición / Color", "clave": "cine", "accent": "#10B981", "accent_2": "#FBBF24", "ground": "#0F172A", "surface": "#111C32", "ink": "#ECFDF5", "font_display": "Space Grotesk"},
    "tech": {"nombre": "Novedades Tech / Gadgets / Comparativas", "clave": "tech", "accent": "#8B5CF6", "accent_2": "#EC4899", "ground": "#090D16", "surface": "#12142A", "ink": "#F5F3FF", "font_display": "Outfit"},
}

REGLAS: list[tuple[str, tuple[str, ...]]] = [
    ("tips", ("tip", "configuracion", "configuración", "ajuste", "sensor", "checklist", "bateria", "batería", "dji")),
    ("fpv", ("fpv", "accion", "acción", "velocidad", "racing", "freestyle", "veloz", "rapido", "rápido")),
    ("cine", ("cinemat", "edicion", "edición", "color", "toma", "plano", "grade", "aereo", "aéreo")),
    ("tech", ("tech", "tecnolog", "gadget", "comparativa", "novedad", "review", "lanzamiento")),
]


def normalizar(texto: Any) -> str:
    valor = unicodedata.normalize("NFKD", str(texto or ""))
    valor = "".join(caracter for caracter in valor if not unicodedata.combining(caracter))
    return re.sub(r"\s+", " ", valor.casefold()).strip()


def seleccionar(categoria: Any, titulo: Any = "") -> str:
    for texto in (normalizar(categoria), normalizar(titulo)):
        for clave, marcadores in REGLAS:
            if any(marcador in texto for marcador in marcadores):
                return clave
    return "tips"


def datos_paleta(clave: str) -> dict[str, Any]:
    if clave not in PALETAS:
        raise ValueError(f"Paleta desconocida: {clave}")
    return dict(PALETAS[clave])


def guardar_en_proyecto(proyecto: Path, categoria: Any, titulo: Any = "") -> dict[str, Any]:
    proyecto = Path(proyecto).resolve()
    if not proyecto.is_dir():
        raise FileNotFoundError(f"No existe el proyecto {proyecto}")
    clave = seleccionar(categoria, titulo)
    paleta = datos_paleta(clave)

    config_path = proyecto / "config.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        config = {}
    if not isinstance(config, dict):
        config = {}
    config["categoria"] = str(categoria or "")
    config["titulo"] = str(titulo or "")
    config["paleta"] = paleta
    config["zonas_visuales"] = {
        "superior": {"top": 200, "bottom": 340, "left": 80, "right": 150, "contenido": "subtítulo dinámico corto, píldora de sección y puntos de progreso"},
        "central": {"top": 380, "bottom": 1260, "left": 80, "right": 150, "contenido": "tarjeta protagonista animada con SVG vectoriales y micro-estímulos"},
        "inferior_vacia_desde": 1320,
    }
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    metadata_path = proyecto / "renders" / "metadata.json"
    if metadata_path.is_file():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            metadata = {}
        if isinstance(metadata, dict):
            metadata["paleta"] = paleta
            metadata["paleta_clave"] = clave
            metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return paleta


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Selecciona y guarda la paleta visual de un proyecto.")
    parser.add_argument("proyecto", help="Carpeta del proyecto")
    parser.add_argument("categoria", help="Categoría del video")
    parser.add_argument("--titulo", default="", help="Título del video para afinar la selección")
    parser.add_argument("--solo-clave", action="store_true", help="Imprime solo la clave de la paleta")
    args = parser.parse_args(argv)
    try:
        paleta = guardar_en_proyecto(Path(args.proyecto), args.categoria, args.titulo)
    except (OSError, ValueError) as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 1
    print(paleta["clave"] if args.solo_clave else json.dumps(paleta, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
