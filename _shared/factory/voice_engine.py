from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path
from typing import Any

PUBLISHER_DIR = Path(__file__).resolve().parent.parent / "publisher"
if str(PUBLISHER_DIR) not in sys.path:
    sys.path.insert(0, str(PUBLISHER_DIR))

import texto_utf8

VOZ_JORGE = "es-MX-JorgeNeural"
VOZ_DALIA = "es-MX-DaliaNeural"
VOZ_ANDREW = "en-US-AndrewNeural"
IDIOMAS = ("es", "en")
VOZ_VALIDAS = {VOZ_JORGE, VOZ_DALIA, VOZ_ANDREW}
VOZ_POR_IDIOMA = {"es": VOZ_DALIA, "en": VOZ_ANDREW}
VOCES = {"es": (VOZ_JORGE, VOZ_DALIA), "en": (VOZ_ANDREW,)}

VOZES_POR_CLAVE = {
    "tips": VOZ_DALIA,
    "fpv": VOZ_JORGE,
    "cine": VOZ_JORGE,
    "tech": VOZ_DALIA,
}

PRONUNCIACION = {
    "es": {
        "FPS": "cuadros por segundo",
        "AUX": "auxiliar",
        "FPV": "efe pe uve",
    },
    "en": {
        "FPS": "frames per second",
        "AUX": "aux input",
        "FPV": "F P V",
    },
}

CONECTORES = [
    "entonces",
    "ahora",
    "primero",
    "después",
    "sin embargo",
    "por eso",
    "lo importante",
    "además",
    "por ejemplo",
    "al final",
    "recuerda",
]

CONECTORES_EN = [
    "now",
    "first",
    "then",
    "however",
    "that is why",
    "the key",
    "also",
    "for example",
    "in the end",
    "remember",
]


def normalizar(texto: Any) -> str:
    normalizado = re.sub(
        r"[\u0300-\u036f]",
        "",
        unicodedata.normalize("NFD", texto_utf8.limpiar_utf8(texto)),
    )
    return re.sub(r"\s+", " ", normalizado).strip().lower()


def elegir_voz(categoria: Any = "", titulo: Any = "", voz: Any = "", idioma: Any = "es") -> str:
    idioma_resuelto = resolver_idioma(idioma)
    voces = VOCES[idioma_resuelto]
    forzada = texto_utf8.limpiar_utf8(voz).strip()
    if forzada:
        if forzada not in voces:
            raise ValueError(f"Voz no soportada: {forzada}")
        return forzada
    if idioma_resuelto == "en":
        return VOZ_ANDREW
    base = normalizar(f"{categoria} {titulo}")
    if any(marcador in base for marcador in ("tips", "configuracion", "tutorial", "educativo", "explicacion", "cine", "cinematograf")):
        preferida = VOZ_DALIA
    else:
        preferida = VOZ_JORGE
    semilla = sum(ord(c) for c in base) if base else 0
    return preferida if semilla % 2 == 0 else (VOZ_JORGE if preferida == VOZ_DALIA else VOZ_DALIA)


def limpiar_siglas(texto: Any, idioma: str = "es") -> str:
    resultado = texto_utf8.limpiar_utf8(texto)
    for sigla, hablado in PRONUNCIACION[idioma].items():
        resultado = re.sub(
            rf"(?<!\w){re.escape(sigla)}(?!\w)",
            hablado,
            resultado,
            flags=re.IGNORECASE,
        )
    return resultado


def agregar_pausas(texto: Any, idioma: str = "es") -> str:
    resultado = limpiar_siglas(texto, idioma)
    resultado = resultado.replace(";", ",")
    conectores = CONECTORES_EN if idioma == "en" else CONECTORES
    for conector in conectores:
        patron = rf"(?i)\b{re.escape(conector)}\b(?=\s)(?!,)"
        resultado = re.sub(patron, lambda coincidencia: coincidencia.group(0) + ",", resultado)
    resultado = re.sub(r"\s+", " ", resultado).strip()
    resultado = re.sub(r"\s+([,.;:!?])", r"\1", resultado)
    if resultado and resultado[-1] not in ".!?":
        resultado += "."
    return resultado


def oraciones(texto: Any) -> list[str]:
    crudo = re.split(r"(?<=[.!?])\s+", texto_utf8.limpiar_utf8(texto).strip())
    return [parte.strip() for parte in crudo if parte.strip()]


def agrupar(oraciones_texto: list[str], limite: int = 220) -> list[str]:
    grupos: list[str] = []
    actual = ""
    for oracion in oraciones_texto:
        candidato = f"{actual} {oracion}".strip()
        if actual and len(candidato) > limite:
            grupos.append(actual)
            actual = oracion
        else:
            actual = candidato
    if actual:
        grupos.append(actual)
    return grupos


def preparar_segmentos(texto: Any, idioma: str = "es") -> list[dict[str, str]]:
    hablado = agregar_pausas(texto, idioma)
    partes = oraciones(hablado)
    if not partes:
        return []

    segmentos: list[dict[str, str]] = [
        {"texto": partes[0], "rate": "+8%", "pitch": "+3Hz", "rol": "gancho"}
    ]
    for grupo in agrupar(partes[1:]):
        segmentos.append({"texto": grupo, "rate": "+3%", "pitch": "+0Hz", "rol": "cuerpo"})
    return segmentos


def resolver_idioma(idioma: Any) -> str:
    valor = texto_utf8.limpiar_utf8(idioma).strip().casefold() or "es"
    if valor not in IDIOMAS:
        raise ValueError(f"Idioma no soportado: {valor}; usa es o en")
    return valor


def cargar_texto_adaptado(salida: Path | str, idioma: str, texto_en: Any = "") -> tuple[str, bool]:
    if idioma != "en":
        return texto_utf8.limpiar_utf8(texto_en), False
    adaptado = texto_utf8.limpiar_utf8(texto_en).strip()
    if adaptado:
        return adaptado, False

    ruta = Path(salida).expanduser().resolve()
    carpetas = [ruta.parent] + list(ruta.parents)[:3]
    for carpeta in carpetas:
        json_path = carpeta / "guion.en.json"
        if json_path.is_file():
            try:
                datos = json.loads(json_path.read_text(encoding="utf-8", errors="replace"))
            except (OSError, json.JSONDecodeError):
                continue
            clave = "texto" if isinstance(datos, dict) else ""
            valor = texto_utf8.limpiar_utf8(datos.get(clave)).strip() if clave else ""
            if valor:
                return valor, False
        txt_path = carpeta / "guion.en.txt"
        if txt_path.is_file():
            valor = texto_utf8.limpiar_utf8(txt_path.read_text(encoding="utf-8", errors="replace")).strip()
            if valor:
                return valor, False
    return "[English adaptation required: create guion.en.json or pass --texto-en]", True


def ruta_ffmpeg() -> str:
    return str(os.getenv("FFMPEG_BIN") or shutil.which("ffmpeg") or "ffmpeg")


async def generar_audio(
    texto: str,
    salida: Path,
    voz: str,
    rate: str,
    pitch: str,
) -> list[dict[str, Any]]:
    import edge_tts

    comunicacion = edge_tts.Communicate(
        texto, voice=voz, rate=rate, pitch=pitch, boundary="WordBoundary"
    )
    limites: list[dict[str, Any]] = []
    with salida.open("wb") as archivo:
        async for parte in comunicacion.stream():
            if parte["type"] == "audio":
                archivo.write(parte["data"])
            elif parte["type"] == "WordBoundary":
                limites.append(
                    {
                        "text": str(parte.get("text", "")),
                        "offset_s": round(float(parte.get("offset", 0)) / 10_000_000, 4),
                        "duration_s": round(float(parte.get("duration", 0)) / 10_000_000, 4),
                    }
                )
    return limites


def _duracion_ffprobe(ruta: Path) -> float:
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(ruta)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return max(0.0, float((r.stdout or "0").strip()))
    except Exception:
        return 0.0


def aplicar_silenceremove(entrada: Path, salida: Path) -> dict[str, Any]:
    salida.parent.mkdir(parents=True, exist_ok=True)
    dur_antes = _duracion_ffprobe(entrada)
    filtro = "silenceremove=start_periods=1:start_duration=0.05:start_threshold=-45dB,areverse,silenceremove=start_periods=1:start_duration=0.05:start_threshold=-45dB,areverse"
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(entrada), "-af", filtro, "-c:a", "libmp3lame", "-b:a", "192k", str(salida)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not salida.exists():
        shutil.copyfile(entrada, salida)
        return {"antes_s": round(dur_antes, 4), "despues_s": round(dur_antes, 4), "recortado": False}
    return {"antes_s": round(dur_antes, 4), "despues_s": round(_duracion_ffprobe(salida), 4), "recortado": True}


def concatenar(segmentos: list[Path], salida: Path) -> None:
    salida.parent.mkdir(parents=True, exist_ok=True)
    if len(segmentos) == 1:
        shutil.copyfile(segmentos[0], salida)
        return
    lista = salida.parent / f"{salida.stem}.concat.txt"
    contenido = "".join(f"file '{segmento.as_posix()}'\n" for segmento in segmentos)
    lista.write_text(contenido, encoding="utf-8")
    comando = [ruta_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lista), "-c:a", "libmp3lame", "-b:a", "192k", "-ar", "48000", str(salida)]
    try:
        resultado = subprocess.run(comando, capture_output=True, text=True)
        if resultado.returncode != 0:
            raise RuntimeError((resultado.stderr or resultado.stdout).strip() or "ffmpeg concat falló")
    finally:
        lista.unlink(missing_ok=True)
    if resultado.returncode != 0:
        detalle = (resultado.stderr or resultado.stdout).strip()
        raise RuntimeError(f"No se pudo unir la voz: {detalle}")


def generar_voz(
    texto: Any,
    salida: Path | str,
    categoria: Any = "",
    titulo: Any = "",
    voz: Any = "",
    dry_run: bool = False,
    idioma: str = "es",
    texto_en: Any = "",
) -> dict[str, Any]:
    idioma_resuelto = resolver_idioma(idioma)
    adaptado, requiere_adaptacion = cargar_texto_adaptado(salida, idioma_resuelto, texto_en)
    if requiere_adaptacion and not dry_run:
        raise RuntimeError(
            "Para --idioma en entrega --texto-en o crea guion.en.json con la clave 'texto'; "
            "el pipeline no traduce automáticamente sin revisión humana."
        )
    escrito = adaptado if idioma_resuelto == "en" else texto_utf8.limpiar_utf8(texto)
    voz_elegida = elegir_voz(categoria, titulo, voz, idioma=idioma_resuelto)
    segmentos = preparar_segmentos(escrito, idioma=idioma_resuelto)
    hablado = " ".join(segmento["texto"] for segmento in segmentos)
    ruta = Path(salida).expanduser().resolve()
    sidecar = ruta.with_suffix(".json")
    resultado: dict[str, Any] = {
        "ruta": str(ruta),
        "sidecar": str(sidecar),
        "voz": voz_elegida,
        "idioma": idioma_resuelto,
        "requiere_adaptacion": requiere_adaptacion,
        "texto_escrito": escrito,
        "texto_hablado": hablado,
        "segmentos": [
            {**s, "inicio": round(sum(max(0.6, len(str(x.get("texto","")).split())/2.6)+0.18 for x in segmentos[:i]),3), "duracion_estimada": round(max(0.6, len(str(s.get("texto","")).split())/2.6),3)}
            for i, s in enumerate(segmentos)
        ],
        "dry_run": dry_run,
    }
    if dry_run:
        return resultado

    ruta.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    with tempfile.TemporaryDirectory(prefix="aura-voz-") as temporal:
        directorio = Path(temporal)
        archivos: list[Path] = []
        boundaries_all: list[dict[str, Any]] = []
        cursor_s = 0.0
        for indice, segmento in enumerate(segmentos):
            destino = directorio / f"segmento-{indice:02d}.mp3"
            bounds = asyncio.run(
                generar_audio(
                    segmento["texto"],
                    destino,
                    voz=voz_elegida,
                    rate=segmento["rate"],
                    pitch=segmento["pitch"],
                )
            )
            seg_dur = _duracion_ffprobe(destino)
            for b in bounds:
                boundaries_all.append({"text": b.get("text", ""), "offset_s": round(cursor_s + float(b.get("offset_s", 0)), 4), "duration_s": float(b.get("duration_s", 0))})
            cursor_s += seg_dur
            archivos.append(destino)
        bruto = ruta.with_name(f".{ruta.stem}.bruto.mp3")
        concatenar(archivos, bruto)
        info_silencio = aplicar_silenceremove(bruto, ruta)
        bruto.unlink(missing_ok=True)
    dur_real = _duracion_ffprobe(ruta)
    recorte_inicio = max(0.0, float(info_silencio.get("antes_s", 0)) - float(info_silencio.get("despues_s", 0)))
    for b in boundaries_all:
        b["offset_s"] = round(max(0.0, b["offset_s"] - min(recorte_inicio, 0.5)), 4)
    resultado["duracion_real_s"] = round(dur_real, 4)
    resultado["silenceremove"] = info_silencio
    resultado["word_boundaries"] = boundaries_all
    timing_path = ruta.parent / "subtitles_timing.json"
    timing_path.write_text(json.dumps({
        "audio": str(ruta), "duracion_real_s": round(dur_real, 4), "idioma": idioma_resuelto, "voz": voz_elegida,
        "words": boundaries_all, "segmentos": resultado.get("segmentos", []),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    resultado["subtitles_timing"] = str(timing_path)
    sidecar.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return resultado


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Voz conversacional edge-tts con prosodia por segmento.")
    parser.add_argument("texto", help="Guion a narrar")
    parser.add_argument("salida", help="Ruta del MP3 de salida")
    parser.add_argument("--categoria", default="", help="Categoría del video para elegir voz")
    parser.add_argument("--titulo", default="", help="Título del video para elegir voz")
    parser.add_argument(
        "--voz", default="", help=f"Voz edge-tts: {VOZ_JORGE}, {VOZ_DALIA} o {VOZ_ANDREW}"
    )
    parser.add_argument("--idioma", choices=IDIOMAS, default="es", help="Idioma de la narración")
    parser.add_argument("--texto-en", default="", help="Guion adaptado al inglés, ya revisado")
    parser.add_argument("--dry-run", action="store_true", help="Muestra el plan sin generar audio")
    args = parser.parse_args(argv)

    resultado = generar_voz(
        args.texto,
        args.salida,
        categoria=args.categoria,
        titulo=args.titulo,
        voz=args.voz,
        dry_run=args.dry_run,
        idioma=args.idioma,
        texto_en=args.texto_en,
    )
    print(json.dumps(resultado, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
