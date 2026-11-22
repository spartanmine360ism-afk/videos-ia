from __future__ import annotations

import argparse
import json
import os
import random
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT_DIR = Path(__file__).resolve().parents[2]
MUSIC_DIR = ROOT_DIR / "_shared" / "music"
CARPETAS = ("fpv_ritmo", "tech_lofi", "cine_epico")
CARPETAS_LEGACY = ("fpv_energia", "cine_ambiental", "tech_limpio")
EXTENSIONES = ("*.mp3", "*.wav")
MARCADORES = {
    "fpv_ritmo": ("fpv", "accion", "velocidad", "racing", "freestyle", "avata"),
    "cine_epico": ("cine", "toma", "plano", "edicion", "color", "aereo", "dji", "epico"),
    "tech_lofi": ("tech", "tecnolog", "gadget", "comparativa", "novedad", "review", "tip"),
}


def limpiar(texto: Any) -> str:
    return re.sub(r"\s+", " ", str(texto or "")).strip()


def normalizar(texto: Any) -> str:
    valor = unicodedata.normalize("NFKD", limpiar(texto))
    valor = "".join(c for c in valor if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", valor.casefold()).strip()


def ruta_ffmpeg() -> str:
    return str(os.getenv("FFMPEG_BIN") or shutil.which("ffmpeg") or "ffmpeg")


def ruta_ffprobe() -> str:
    return str(os.getenv("FFPROBE_BIN") or shutil.which("ffprobe") or "ffprobe")


def duracion(archivo: Path) -> float:
    cmd = [ruta_ffprobe(), "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(archivo)]
    r = subprocess.run(cmd, text=True, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffprobe no pudo medir {archivo.name}")
    try:
        return max(1.0, float((r.stdout or "0").strip()))
    except ValueError as e:
        raise RuntimeError(f"Duración inválida en {archivo.name}") from e


def _asegurar_musica_base() -> None:
    # genera pistas base WAV simples si no hay música
    existentes = []
    for c in CARPETAS + CARPETAS_LEGACY:
        existentes.extend(pistas(MUSIC_DIR / c))
    if existentes:
        return
    import math, wave, struct
    sr = 44100
    specs = {"fpv_ritmo": (110, 140), "tech_lofi": (90, 86), "cine_epico": (70, 96)}
    for name, (f0, bpm) in specs.items():
        p = MUSIC_DIR / name / f"{name}_base.wav"
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists():
            continue
        dur = 30
        n = int(sr * dur)
        beat = int(sr * 60 / bpm)
        peak = 1e-6
        samples = []
        for i in range(n):
            t = i / sr
            v = 0.12 * math.sin(2 * math.pi * f0 * t) * (0.7 + 0.3 * math.sin(2 * math.pi * 0.1 * t))
            v += 0.06 * math.sin(2 * math.pi * f0 * 2 * t)
            if i % beat < int(sr * 0.04):
                v += 0.08 * math.exp(-(i % beat) / (sr * 0.01))
            env = 1.0
            if i < sr * 0.5:
                env = i / (sr * 0.5)
            if i > n - sr:
                env = max(0.0, (n - i) / sr)
            v *= env
            peak = max(peak, abs(v))
            samples.append(v)
        with wave.open(str(p), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
            for s in samples:
                w.writeframes(struct.pack("<h", int(max(-1, min(1, s / peak * 0.6)) * 32767)))


def clave_categoria(categoria: Any, proyecto: Path) -> str:
    texto_categoria = normalizar(limpiar(categoria))
    for clave, marcadores in MARCADORES.items():
        if any(m in texto_categoria for m in marcadores):
            return clave
    textos = [limpiar(categoria)]
    for ruta in (proyecto / "config.json", proyecto / "renders" / "metadata.json"):
        if ruta.is_file():
            try:
                textos.append(json.dumps(json.loads(ruta.read_text(encoding="utf-8", errors="replace")), ensure_ascii=False))
            except Exception:
                pass
    texto = normalizar(" ".join(textos))
    for clave, marcadores in MARCADORES.items():
        if any(m in texto for m in marcadores):
            return clave
    return "tech_lofi"


def pistas(carpeta: Path) -> list[Path]:
    if not carpeta.is_dir():
        return []
    hallazgos = []
    for ext in EXTENSIONES:
        hallazgos.extend(a for a in carpeta.glob(ext) if a.is_file())
    return sorted(hallazgos, key=lambda a: a.name)


def elegir_pista(categoria: Any, proyecto: Path, semilla: str = "") -> tuple[Path | None, str]:
    preferida = clave_categoria(categoria, proyecto)
    orden = [preferida] + [c for c in CARPETAS if c != preferida] + list(CARPETAS_LEGACY)
    for nombre in orden:
        disponibles = pistas(MUSIC_DIR / nombre)
        if not disponibles:
            continue
        sel = random.Random(f"{semilla}|{nombre}").choice(disponibles)
        return sel, nombre
    return None, preferida


def detectar_frase_clave_s(voz: Path, proyecto: Path) -> float | None:
    # heurística: último segmento del sidecar voz.json, o 70% de duración
    for ruta in (voz.with_suffix('.json'), proyecto / 'assets' / 'audio' / 'voz.json', proyecto / 'renders' / 'voz.json'):
        if not ruta.is_file():
            continue
        try:
            data = json.loads(ruta.read_text(encoding='utf-8'))
        except Exception:
            continue
        segs = data.get('segmentos') or data.get('segments') or []
        if isinstance(segs, list) and segs:
            ultimo = segs[-1]
            inicio = ultimo.get('inicio') or ultimo.get('start') or ultimo.get('t0')
            try:
                t = float(inicio)
                if t > 1.0:
                    return t
            except Exception:
                pass
        dur = data.get('duracion_seg') or data.get('duration')
        try:
            d = float(dur)
            if d > 3:
                return max(1.0, d - 2.5)
        except Exception:
            pass
    try:
        d = duracion(voz)
        return max(1.0, d - 2.5)
    except Exception:
        return None


def filtro_duck(segundos: float, volumen_base: float, frase_clave_s: float | None) -> str:
    # -20 dB aprox = 0.1; mantenemos parámetro pero normalizamos a rango seguro
    vol = max(0.03, min(0.2, volumen_base))
    vol_txt = f"{vol:.4f}".rstrip('0').rstrip('.')
    # silencio dramático 0.5s antes de frase clave: multiplicar volumen por 0 en ventana
    silencio = ""
    if frase_clave_s is not None and 0.6 < frase_clave_s < segundos - 0.6:
        t0 = max(0.0, frase_clave_s - 0.5)
        t1 = min(segundos, frase_clave_s)
        silencio = f",volume=enable='between(t,{t0:.2f},{t1:.2f})':volume=0"
    return (
        f"[1:a]aformat=channel_layouts=stereo,apad=pad_dur={segundos:.2f},"
        f"atrim=0:{segundos:.2f},asetpts=PTS-STARTPTS,volume={vol_txt}{silencio}[base];"
        f"[base][0:a]sidechaincompress=threshold=0.02:ratio=8:attack=20:release=350:makeup=1[duck];"
        f"[duck]alimiter=limit=0.891[ducklim]"
    )


def mezclar(proyecto: Path, categoria: Any, voz: Path, salida: Path, volumen: float = 0.1, semilla: str = "") -> dict[str, Any]:
    if not voz.is_file():
        raise RuntimeError(f"No existe la voz: {voz}")
    _asegurar_musica_base()
    pista, carpeta = elegir_pista(categoria, proyecto, semilla or proyecto.name)
    if pista is None:
        return {"estado": "sin_pista", "mensaje": f"No hay música en {MUSIC_DIR}", "carpeta": carpeta}
    segundos = duracion(voz)
    frase = detectar_frase_clave_s(voz, proyecto)
    salida.parent.mkdir(parents=True, exist_ok=True)
    filtro = filtro_duck(segundos, volumen, frase)
    cmd = [
        ruta_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(voz), "-i", str(pista),
        "-filter_complex", filtro,
        "-map", "[ducklim]", "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", str(salida),
    ]
    r = subprocess.run(cmd, text=True, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"FFmpeg ducking falló: {(r.stderr or r.stdout).strip()}")
    return {"estado": "ducked", "carpeta": carpeta, "pista": str(pista), "salida": str(salida), "duracion_s": round(segundos,2), "frase_clave_s": frase, "volumen_base": volumen}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Mezcla música con auto-ducking y silencio dramático.")
    ap.add_argument("--proyecto", default=".")
    ap.add_argument("--categoria", default="")
    ap.add_argument("--voz", default="assets/audio/voz.mp3")
    ap.add_argument("--salida", default="assets/audio/musica_duck.wav")
    ap.add_argument("--volumen", type=float, default=0.1)
    ap.add_argument("--semilla", default="")
    args = ap.parse_args(argv)
    proyecto = Path(args.proyecto).expanduser().resolve()
    voz = Path(args.voz)
    if not voz.is_absolute():
        voz = proyecto / voz
    salida = Path(args.salida)
    if not salida.is_absolute():
        salida = proyecto / salida
    try:
        res = mezclar(proyecto, args.categoria, voz.resolve(), salida, volumen=max(0.03, min(0.2, args.volumen)), semilla=args.semilla)
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 2
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
