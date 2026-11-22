import hashlib
import json
import re
from pathlib import Path


PALETAS_POR_TEMA = {
    "dron-fpv-tecnico": {
        "fondo": "#101820",
        "superficie": "#1b2836",
        "acento_primario": "#00b4d8",
        "acento_secundario": "#f77f00",
        "texto_principal": "#f8fafc",
        "texto_secundario": "#cbd5e1",
        "estilo_visual": "hud-diagrama-tecnico",
    },
    "terror-personajes": {
        "fondo": "#161114",
        "superficie": "#261b20",
        "acento_primario": "#c92a2a",
        "acento_secundario": "#d4a373",
        "texto_principal": "#f3efe6",
        "texto_secundario": "#c7b8b0",
        "estilo_visual": "narrativa-atmosferica-2d-3d",
    },
    "negocios-marca-local": {
        "fondo": "#faf7f2",
        "superficie": "#ffffff",
        "acento_primario": "#d9480f",
        "acento_secundario": "#1864ab",
        "texto_principal": "#1e293b",
        "texto_secundario": "#475569",
        "estilo_visual": "editorial-dinamico-hud",
    },
    "educacion-diagramas": {
        "fondo": "#f4f7fb",
        "superficie": "#ffffff",
        "acento_primario": "#0f766e",
        "acento_secundario": "#2563eb",
        "texto_principal": "#0f172a",
        "texto_secundario": "#334155",
        "estilo_visual": "diagramas-claros-2d",
    },
}


def _leer_contexto_proyecto(proyecto_dir: Path, tema_override: str = "") -> str:
    partes = [tema_override, proyecto_dir.name.replace("-", " ").replace("_", " ")]
    for rel in ["tema.txt", "guion.md", "guion.txt", "meta.json", "config.json", "index.html"]:
        p = proyecto_dir / rel
        if p.exists() and p.is_file():
            try:
                partes.append(p.read_text(encoding="utf-8", errors="ignore")[:3000])
            except Exception:
                pass
    return " ".join(partes).strip()


def _paleta_independiente_por_hash(semilla: str) -> dict:
    digest = hashlib.sha256(semilla.encode("utf-8")).hexdigest()
    h1, h2, h3 = digest[0:6], digest[6:12], digest[12:18]
    # Asegura contraste entre fondo y texto usando luminancia simple
    r = int(h1[0:2], 16)
    g = int(h1[2:4], 16)
    b = int(h1[4:6], 16)
    luminancia = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
    es_claro = luminancia > 0.52
    return {
        "fondo": f"#{h1}",
        "superficie": "#ffffff" if es_claro else "#1e2430",
        "acento_primario": f"#{h2}",
        "acento_secundario": f"#{h3}",
        "texto_principal": "#111827" if es_claro else "#f9fafb",
        "texto_secundario": "#374151" if es_claro else "#d1d5db",
        "estilo_visual": "identidad-independiente-2d-3d",
    }


def generar_direccion_creativa(proyecto_dir: Path, tema_override: str = "", duracion_seg: float = 30.0) -> dict:
    contexto = _leer_contexto_proyecto(proyecto_dir, tema_override)
    txt = contexto.lower()
    duracion_limpia = max(1.0, min(60.0, float(duracion_seg)))

    if any(k in txt for k in ["fpv", "dron", "dji", "telemetria", "vuelo", "hud"]):
        categoria = "dron-fpv-tecnico"
        paleta = dict(PALETAS_POR_TEMA[categoria])
    elif any(k in txt for k in ["terror", "horror", "personaje", "caracterizacion", "suspenso"]):
        categoria = "terror-personajes"
        paleta = dict(PALETAS_POR_TEMA[categoria])
    elif any(k in txt for k in ["pollo", "parrilla", "negocio", "promo", "local", "marca", "venta"]):
        categoria = "negocios-marca-local"
        paleta = dict(PALETAS_POR_TEMA[categoria])
    elif any(k in txt for k in ["diagrama", "explicar", "tutorial", "paso", "flujo", "arquitectura"]):
        categoria = "educacion-diagramas"
        paleta = dict(PALETAS_POR_TEMA[categoria])
    else:
        categoria = "tema-libre-unico"
        paleta = _paleta_independiente_por_hash(contexto or proyecto_dir.name)

    # Si el proyecto o tema indica un color hex explícito, respetarlo
    m_hex = re.search(r"#([0-9a-fA-F]{6})", txt)
    if m_hex:
        paleta["fondo"] = f"#{m_hex.group(1)}"

    direccion = {
        "proyecto": proyecto_dir.name,
        "categoria_tema": categoria,
        "duracion_max_seg": 60.0,
        "duracion_objetivo_seg": duracion_limpia,
        "idioma": "es-MX",
        "reglas_fijas": {
            "duracion_menor_igual_60s": True,
            "espanol_natural_obligatorio": True,
            "sin_textos_encimados": True,
            "identidad_propia_por_video": True,
        },
        "paleta": paleta,
        "enfoque_recursos": {
            "diagramas_y_hud": "adaptados al tema sin imponer fondo oscuro universal",
            "animacion_2d_3d": "seleccionada segun la historia y el ritmo del tema",
        },
    }

    out_path = proyecto_dir / "direccion_creativa.json"
    if proyecto_dir.exists():
        out_path.write_text(json.dumps(direccion, ensure_ascii=False, indent=2), encoding="utf-8")
    return direccion
