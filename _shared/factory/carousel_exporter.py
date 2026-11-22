from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import paletas

ANCHO = 1080
ALTO = 1350
FUENTES = (
    r"C:\Windows\Fonts\segoeuib.ttf",
    r"C:\Windows\Fonts\bahnschrift.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
    "DejaVuSans-Bold.ttf",
    r"C:\Windows\Fonts\segoeui.ttf",
)


def limpiar(texto: Any) -> str:
    return re.sub(r"\s+", " ", str(texto or "")).strip()


def rgb(color: Any, fallback: tuple[int, int, int] = (255, 255, 255)) -> tuple[int, int, int]:
    valor = limpiar(color).lstrip("#")
    if len(valor) == 3:
        valor = "".join(caracter * 2 for caracter in valor)
    if len(valor) != 6:
        return fallback
    try:
        return tuple(int(valor[index : index + 2], 16) for index in (0, 2, 4))
    except ValueError:
        return fallback


def fuente(tamano: int) -> Any:
    from PIL import ImageFont

    for candidata in FUENTES:
        try:
            return ImageFont.truetype(candidata, tamano)
        except OSError:
            continue
    return ImageFont.load_default()


def palabras(texto: str, fuente_usada: Any, ancho_max: int, dibujo: Any) -> list[str]:
    lineas: list[str] = []
    actual = ""
    for palabra in texto.split():
        candidato = f"{actual} {palabra}".strip()
        caja = dibujo.textbbox((0, 0), candidato, font=fuente_usada)
        if actual and caja[2] - caja[0] > ancho_max:
            lineas.append(actual)
            actual = palabra
        else:
            actual = candidato
    if actual:
        lineas.append(actual)
    return lineas


def oraciones(texto: str) -> list[str]:
    bruto = re.split(r"(?<=[.!?])\s+|\n+", texto)
    return [limpiar(parte) for parte in bruto if limpiar(parte)]


def puntos_desde(texto: Any, titulo: str) -> list[str]:
    encontradas = oraciones(limpiar(texto))
    if len(encontradas) >= 3:
        indices = (0, len(encontradas) // 2, len(encontradas) - 1)
        seleccionadas = [encontradas[indice] for indice in indices]
    else:
        seleccionadas = list(encontradas)
    while len(seleccionadas) < 3:
        seleccionadas.append(titulo or "Aura Drones")
    return [limpiar(punto)[:180] for punto in seleccionadas]


def leer_puntos(proyecto: Path, puntos: list[str] | None, titulo: str) -> list[str]:
    if puntos:
        return puntos_desde(" ".join(puntos), titulo)

    for nombre in ("carrusel/puntos.json", "puntos_carrusel.json"):
        ruta = proyecto / nombre
        if ruta.is_file():
            try:
                datos = json.loads(ruta.read_text(encoding="utf-8", errors="replace"))
            except (OSError, json.JSONDecodeError):
                continue
            valores = datos.get("puntos") if isinstance(datos, dict) else datos
            if isinstance(valores, list) and valores:
                return puntos_desde(" ".join(str(valor) for valor in valores), titulo)

    voz = proyecto / "assets" / "audio" / "voz.json"
    if voz.is_file():
        try:
            datos = json.loads(voz.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            datos = {}
        segmentos = datos.get("segmentos") if isinstance(datos, dict) else []
        textos = [
            segmento.get("texto", "")
            for segmento in segmentos
            if isinstance(segmento, dict) and segmento.get("texto")
        ]
        if textos:
            return puntos_desde(" ".join(str(texto) for texto in textos), titulo)
        if datos.get("texto_escrito"):
            return puntos_desde(str(datos["texto_escrito"]), titulo)

    for nombre in ("guion.md", "script.md", "guion.txt", "script.txt"):
        ruta = proyecto / nombre
        if ruta.is_file():
            return puntos_desde(ruta.read_text(encoding="utf-8", errors="replace"), titulo)

    metadata = proyecto / "renders" / "metadata.json"
    if metadata.is_file():
        try:
            datos = json.loads(metadata.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            datos = {}
        youtube = datos.get("youtube") if isinstance(datos, dict) else None
        if isinstance(youtube, dict):
            texto = limpiar(youtube.get("description"))
            if texto:
                return puntos_desde(texto, titulo)

    return puntos_desde(titulo, titulo)


def paleta_proyecto(proyecto: Path, categoria: str, titulo: str) -> dict[str, Any]:
    for ruta in (proyecto / "config.json", proyecto / "renders" / "metadata.json"):
        if not ruta.is_file():
            continue
        try:
            datos = json.loads(ruta.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            continue
        paleta = datos.get("paleta") if isinstance(datos, dict) else None
        if isinstance(paleta, dict) and paleta.get("accent"):
            return paleta
    return paletas.datos_paleta(paletas.seleccionar(categoria, titulo))


def cta_proyecto(proyecto: Path) -> str:
    ruta = proyecto / "renders" / "metadata.json"
    if not ruta.is_file():
        return ""
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(datos, dict):
        return ""
    youtube = datos.get("youtube")
    if isinstance(youtube, dict):
        pregunta = limpiar(youtube.get("pregunta_detonadora"))
        if pregunta:
            return pregunta
        lineas = [limpiar(linea) for linea in str(youtube.get("description", "")).splitlines() if limpiar(linea)]
        if lineas:
            return oraciones(lineas[-1])[-1] if oraciones(lineas[-1]) else lineas[-1]
    return ""


def dibujar_tarjeta(punto: str, indice: int, total: int, paleta: dict[str, Any], cta: str) -> Any:
    from PIL import Image, ImageDraw

    fondo = rgb(paleta.get("ground"), (10, 12, 18))
    superficie = rgb(paleta.get("surface"), (20, 24, 34))
    acento = rgb(paleta.get("accent"), (0, 229, 255))
    acento_2 = rgb(paleta.get("accent_2"), (244, 251, 255))
    tinta = rgb(paleta.get("ink"), (255, 255, 255))

    imagen = Image.new("RGB", (ANCHO, ALTO), fondo)
    dibujo = ImageDraw.Draw(imagen)
    dibujo.rectangle((0, 0, ANCHO, 16), fill=acento)
    dibujo.ellipse((ANCHO - 360, 90, ANCHO + 160, 610), fill=superficie)
    dibujo.ellipse((-180, 930, 300, 1410), fill=superficie)

    pequena = fuente(34)
    mediana = fuente(42)
    grande = fuente(78 if len(punto) <= 90 else 64)

    dibujo.text((90, 110), "AURA DRONES", font=pequena, fill=acento_2)
    dibujo.text((90, 190), f"{indice + 1:02d} / {total:02d}", font=pequena, fill=acento)
    dibujo.line((90, 260, ANCHO - 90, 260), fill=acento, width=4)

    lineas = palabras(punto, grande, ANCHO - 180, dibujo)
    y = 390
    altura_linea = 96 if len(punto) <= 90 else 80
    for linea in lineas[:7]:
        dibujo.text((90, y), linea, font=grande, fill=tinta)
        y += altura_linea

    pie = cta if indice == total - 1 and cta else "Guarda este punto y compártelo con tu crew"
    lineas_pie = palabras(pie, mediana, ANCHO - 180, dibujo)
    y_pie = ALTO - 250 - len(lineas_pie) * 54
    dibujo.line((90, y_pie - 40, ANCHO - 90, y_pie - 40), fill=acento, width=4)
    for linea in lineas_pie[:3]:
        dibujo.text((90, y_pie), linea, font=mediana, fill=acento_2)
        y_pie += 54
    dibujo.text((90, ALTO - 80), "1080 x 1350 · Carrusel Aura Drones", font=pequena, fill=acento)
    return imagen


def exportar(
    proyecto: Path,
    puntos: list[str] | None = None,
    titulo: str = "",
    categoria: str = "",
    escribir: bool = True,
) -> dict[str, Any]:
    proyecto = Path(proyecto).expanduser().resolve()
    if not proyecto.is_dir():
        raise FileNotFoundError(f"No existe el proyecto {proyecto}")

    titulo = limpiar(titulo) or json_valor(proyecto, "titulo") or titulo_desde_metadata(proyecto)
    categoria = limpiar(categoria) or json_valor(proyecto, "categoria")
    seleccionados = leer_puntos(proyecto, puntos, titulo)
    paleta = paleta_proyecto(proyecto, categoria, titulo)
    cta = cta_proyecto(proyecto)
    destino = proyecto / "carrusel"

    rutas: list[str] = []
    if escribir:
        destino.mkdir(parents=True, exist_ok=True)
    for indice, punto in enumerate(seleccionados):
        imagen = dibujar_tarjeta(punto, indice, len(seleccionados), paleta, cta)
        ruta = destino / f"{indice + 1:02d}.png"
        rutas.append(ruta.relative_to(proyecto).as_posix())
        if escribir:
            imagen.save(ruta, format="PNG", optimize=True)

    resultado = {
        "estado": "exportado" if escribir else "simulado",
        "proyecto": str(proyecto),
        "tamano": f"{ANCHO}x{ALTO}",
        "paleta_clave": paleta.get("clave", "personalizada"),
        "puntos": seleccionados,
        "cta": cta,
        "imagenes": rutas,
    }
    if escribir:
        manifest = destino / "manifest.json"
        manifest.write_text(
            json.dumps(resultado, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return resultado


def json_valor(proyecto: Path, clave: str) -> str:
    config = proyecto / "config.json"
    if not config.is_file():
        return ""
    try:
        datos = json.loads(config.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return ""
    return limpiar(datos.get(clave)) if isinstance(datos, dict) else ""


def titulo_desde_metadata(proyecto: Path) -> str:
    metadata = proyecto / "renders" / "metadata.json"
    if not metadata.is_file():
        return ""
    try:
        datos = json.loads(metadata.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(datos, dict):
        return ""
    for clave in ("titulo", "title"):
        titulo = limpiar(datos.get(clave))
        if titulo:
            return titulo
    youtube = datos.get("youtube")
    if isinstance(youtube, dict):
        for clave in ("title", "titulo"):
            titulo = limpiar(youtube.get(clave))
            if titulo:
                return titulo
    return ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Exporta 3 imágenes 1080x1350 con la paleta del proyecto.")
    parser.add_argument("proyecto", help="Carpeta del proyecto")
    parser.add_argument("--punto", action="append", default=[], help="Punto clave; repetir hasta 3 veces")
    parser.add_argument("--titulo", default="", help="Título para completar puntos o paleta")
    parser.add_argument("--categoria", default="", help="Categoría para completar la paleta")
    parser.add_argument("--dry-run", action="store_true", help="No escribe las imágenes")
    args = parser.parse_args(argv)

    try:
        resultado = exportar(
            Path(args.proyecto),
            puntos=args.punto or None,
            titulo=args.titulo,
            categoria=args.categoria,
            escribir=not args.dry_run,
        )
    except (FileNotFoundError, OSError, ValueError, RuntimeError) as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 2

    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
