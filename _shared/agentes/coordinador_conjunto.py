import importlib
import pkgutil
from pathlib import Path

from _shared.agentes.agente_direccion_creativa import generar_direccion_creativa
from _shared.agentes.agente_previsualizacion_tema import previsualizar_y_validar_tema


def descubrir_agentes_disponibles() -> list[str]:
    agentes_dir = Path(__file__).resolve().parent
    nombres = []
    for _, name, is_pkg in pkgutil.iter_modules([str(agentes_dir)]):
        if not is_pkg and not name.startswith("_"):
            nombres.append(name)
    return sorted(nombres)


def ejecutar_conjunto_creativo(
    proyecto_dir: Path,
    tema: str = "",
    duracion_seg: float = 30.0,
    correr_render_si_existe: bool = False,
) -> dict:
    """
    Coordina dirección creativa, previsualización del tema y demás módulos en _shared/agentes
    para que trabajen en conjunto con la identidad propia de cada video.
    """
    agentes_detectados = descubrir_agentes_disponibles()
    direccion = generar_direccion_creativa(proyecto_dir, tema_override=tema, duracion_seg=duracion_seg)
    vista = previsualizar_y_validar_tema(direccion, proyecto_dir=proyecto_dir)

    capacidades_conectadas = []
    for modulo in agentes_detectados:
        try:
            importlib.import_module(f"_shared.agentes.{modulo}")
            capacidades_conectadas.append(modulo)
        except Exception:
            continue

    resultado_render = None
    if correr_render_si_existe and "render_segmentado" in capacidades_conectadas:
        mod_render = importlib.import_module("_shared.agentes.render_segmentado")
        if hasattr(mod_render, "renderizar_segmentado_seguro"):
            mp4_out = proyecto_dir / "salida_coordinada.mp4"
            ok, msg = mod_render.renderizar_segmentado_seguro(
                proyecto_dir=proyecto_dir,
                mp4_salida=mp4_out,
                duracion_seg=vista["duracion_validada_seg"],
            )
            resultado_render = {"ok": ok, "mensaje": msg, "mp4": str(mp4_out)}

    return {
        "ok": True,
        "proyecto": str(proyecto_dir),
        "agentes_activos_count": len(capacidades_conectadas),
        "agentes_activos": capacidades_conectadas,
        "direccion_creativa": direccion,
        "previsualizacion_tema": vista,
        "render": resultado_render,
    }
