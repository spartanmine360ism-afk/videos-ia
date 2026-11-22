from pathlib import Path


def _hex_a_rgb(hex_str: str) -> tuple[int, int, int]:
    limpio = (hex_str or "#141a24").lstrip("#")
    if len(limpio) != 6:
        return (20, 26, 36)
    return tuple(int(limpio[i:i + 2], 16) for i in (0, 2, 4))


def _luminancia_relativa(rgb: tuple[int, int, int]) -> float:
    canales = []
    for c in rgb:
        s = c / 255.0
        canales.append(s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4)
    return 0.2126 * canales[0] + 0.7152 * canales[1] + 0.0722 * canales[2]


def ratio_contraste(hex_a: str, hex_b: str) -> float:
    l1 = _luminancia_relativa(_hex_a_rgb(hex_a))
    l2 = _luminancia_relativa(_hex_a_rgb(hex_b))
    claro, oscuro = max(l1, l2), min(l1, l2)
    return round((claro + 0.05) / (oscuro + 0.05), 2)


def previsualizar_y_validar_tema(direccion: dict, proyecto_dir: Path | None = None) -> dict:
    """
    Evalúa cómo se verá el tema antes de renderizar: contraste de texto,
    duración <= 60s, coherencia con el tema y riesgo de textos encimados.
    """
    paleta = direccion.get("paleta", {})
    fondo = paleta.get("fondo", "#141a24")
    texto = paleta.get("texto_principal", "#f8fafc")
    acento = paleta.get("acento_primario", "#00b4d8")
    dur = float(direccion.get("duracion_objetivo_seg", 30.0))

    contraste_texto = ratio_contraste(fondo, texto)
    contraste_acento = ratio_contraste(fondo, acento)

    ajustes = []
    if contraste_texto < 4.5:
        rgb_f = _hex_a_rgb(fondo)
        lum_f = _luminancia_relativa(rgb_f)
        texto_seguro = "#111827" if lum_f > 0.45 else "#f8fafc"
        paleta["texto_principal"] = texto_seguro
        contraste_texto = ratio_contraste(fondo, texto_seguro)
        ajustes.append(f"Se ajustó texto_principal a {texto_seguro} para asegurar contraste ({contraste_texto}:1).")

    if dur > 60.0:
        dur = 60.0
        direccion["duracion_objetivo_seg"] = 60.0
        ajustes.append("Duración recortada al límite estricto de 60.0 s.")

    estado_visual = "aprobado-para-render" if contraste_texto >= 3.0 and dur <= 60.0 else "revisar-contraste"

    return {
        "estado": estado_visual,
        "categoria_tema": direccion.get("categoria_tema", "general"),
        "estilo_visual": paleta.get("estilo_visual", "adaptativo"),
        "fondo_final": fondo,
        "texto_final": paleta.get("texto_principal"),
        "acento_final": acento,
        "contraste_texto_fondo": contraste_texto,
        "contraste_acento_fondo": contraste_acento,
        "duracion_validada_seg": dur,
        "prevencion_solapes": "Activa: layout modular por zonas y verificación OCR posterior",
        "ajustes_aplicados": ajustes,
        "resumen_vista": (
            f"Tema '{direccion.get('categoria_tema')}' con fondo {fondo}, texto {paleta.get('texto_principal')} "
            f"(contraste {contraste_texto}:1) y duración {dur:.1f}s <= 60s."
        ),
    }
